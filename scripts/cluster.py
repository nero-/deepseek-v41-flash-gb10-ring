#!/usr/bin/env python3
"""Configurable cluster control: a curses TUI plus scriptable subcommands.

The cluster (nodes, workloads, actions) comes from a TOML file, by default
config/cluster.toml next to this repository's cluster.sh. Standard library
only; Python 3.11 or newer (tomllib).

  cluster.py                      interactive TUI
  cluster.py status               nodes and workload health, once
  cluster.py list                 workloads and their actions
  cluster.py run WORKLOAD ACTION  run one action (asks first when the action sets confirm)
"""
import argparse
import collections
import concurrent.futures
import curses
import datetime
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO / "config/cluster.toml"
PLACEHOLDERS = ("node", "host", "rank", "user", "repo")

# One SSH round trip per node: host memory, uptime, GPU telemetry, containers and
# GPU processes (FLARE ranks run natively, not in containers) as JSON.
PROBE = r"""
import json, pathlib, subprocess
def run(*a):
    try: return subprocess.run(a, capture_output=True, text=True, timeout=8).stdout.strip()
    except Exception: return ""
def process(pid):
    try: argv = pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().decode().split('\0')
    except OSError: return None
    name = pathlib.Path(argv[0]).name
    return f"{name}:r{argv[argv.index('--rank') + 1]}" if '--rank' in argv[:-1] else name
m = {l.split()[0].rstrip(':'): int(l.split()[1]) for l in pathlib.Path('/proc/meminfo').read_text().splitlines()}
gpu = run('nvidia-smi', '--query-gpu=clocks.sm,utilization.gpu,power.draw,temperature.gpu',
          '--format=csv,noheader,nounits').splitlines()
pids = run('nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader').split()
print(json.dumps({
    'uptime_s': float(pathlib.Path('/proc/uptime').read_text().split()[0]),
    'mem_total_gib': m['MemTotal'] / 2**20, 'mem_used_gib': (m['MemTotal'] - m['MemAvailable']) / 2**20,
    'gpu': [x.strip() for x in gpu[0].split(',')] if gpu else None,
    'containers': run('docker', 'ps', '--format', '{{.Names}}').split(),
    'gpu_processes': [p for p in map(process, pids) if p],
}))
"""


class Config:
    def __init__(self, path: Path):
        self.path = path
        data = tomllib.loads(path.read_text())
        cluster = data.get("cluster", {})
        self.name = cluster.get("name", path.stem)
        self.user = cluster.get("ssh_user", os.environ.get("USER", ""))
        self.ssh_options = list(cluster.get("ssh_options", ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]))
        self.refresh = float(cluster.get("refresh_seconds", 5))
        self.node_actions = list(cluster.get("node_actions", []))
        self.nodes = data.get("nodes", [])
        self.workloads = data.get("workloads", [])
        names = [n["name"] for n in self.nodes]
        if len(set(names)) != len(names) or not all(n.get("host") for n in self.nodes):
            raise SystemExit(f"{path}: every node needs a unique name and a host")
        for workload in self.workloads:
            for action in workload.get("actions", []):
                if action.get("node") and action["node"] not in names:
                    raise SystemExit(f"{path}: action {workload['name']}/{action['name']} names unknown node "
                                     f"{action['node']!r}")

    def node(self, name):
        return next(n for n in self.nodes if n["name"] == name)

    def rank(self, name):
        return [n["name"] for n in self.nodes].index(name)

    def workload(self, name):
        for workload in self.workloads:
            if workload["name"] == name:
                return workload
        raise SystemExit(f"unknown workload {name!r}; known: {', '.join(w['name'] for w in self.workloads)}")

    def action(self, workload, name):
        for action in workload.get("actions", []):
            if action["name"] == name:
                return action
        raise SystemExit(f"{workload['name']} has no action {name!r}; known: "
                         f"{', '.join(a['name'] for a in workload.get('actions', []))}")

    def expand(self, text, node=None):
        values = {"repo": str(REPO), "user": self.user, "node": "", "host": "", "rank": ""}
        if node is not None:
            values.update(node=node["name"], host=node["host"], rank=str(self.rank(node["name"])))
        for key in PLACEHOLDERS:
            text = text.replace("{" + key + "}", values[key])
        return text

    def argv(self, command, node_name=None):
        """The local argv for a command: on a node over SSH, else through the local shell."""
        if node_name is None:
            return ["/bin/bash", "-c", self.expand(command)]
        node = self.node(node_name)
        target = f"{self.user}@{node['name']}" if self.user else node["name"]
        return ["ssh", *self.ssh_options, "-o", f"HostName={node['host']}", target,
                self.expand(command, node)]


def probe_node(config, node):
    started = time.monotonic()
    try:
        r = subprocess.run(config.argv(f"python3 -c {shlex.quote(PROBE)}", node["name"]),
                           capture_output=True, text=True, timeout=15)
        if r.returncode:
            return {"ok": False, "error": (r.stderr.strip().splitlines() or ["ssh failed"])[-1]}
        return {"ok": True, "latency": time.monotonic() - started, **json.loads(r.stdout)}
    except Exception as error:  # timeouts, bad JSON
        return {"ok": False, "error": str(error)}


def health(url, timeout=3.0):
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception:
        return 0


def snapshot(config):
    with concurrent.futures.ThreadPoolExecutor(max(4, len(config.nodes) + len(config.workloads))) as pool:
        nodes = pool.map(lambda n: probe_node(config, n), config.nodes)
        workloads = pool.map(lambda w: health(w.get("health_url")), config.workloads)
        return list(nodes), list(workloads)


def uptime(seconds):
    days, rest = divmod(int(seconds), 86400)
    return f"{days}d{rest // 3600:02d}h" if days else f"{rest // 3600}h{rest % 3600 // 60:02d}m"


def node_row(config, node, state):
    if not state.get("ok"):
        return f"{node['name']:<10} {node.get('role', ''):<7} DOWN  {state.get('error', '')[:60]}"
    gpu = state.get("gpu") or ["-", "-", "-", "-"]
    containers = " ".join(state.get("containers", []) + state.get("gpu_processes", [])) or "-"
    return (f"{node['name']:<10} {node.get('role', ''):<7} up {uptime(state['uptime_s']):>7}  "
            f"mem {state['mem_used_gib']:5.1f}/{state['mem_total_gib']:5.1f}G  "
            f"gpu {gpu[0]:>4}MHz {gpu[1]:>3}% {gpu[2]:>6}W {gpu[3]:>3}C  {containers}")


def health_text(status):
    return {None: "n/a", 0: "down", 200: "healthy"}.get(status, f"HTTP {status}")


def command_status(config, _args):
    nodes, workloads = snapshot(config)
    print(f"{config.name}  {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    for node, state in zip(config.nodes, nodes):
        print(" ", node_row(config, node, state))
    for workload, status in zip(config.workloads, workloads):
        print(f"  {workload['name']:<12} {health_text(status):<8} {workload.get('api', '')}  "
              f"{workload.get('description', '')}")
    return 0 if all(n.get("ok") for n in nodes) else 1


def command_list(config, _args):
    for workload in config.workloads:
        print(f"{workload['name']}: {workload.get('description', '')}")
        for action in workload.get("actions", []):
            where = action.get("node", "local")
            flag = " (confirm)" if action.get("confirm") else ""
            print(f"    {action['name']:<28} on {where}{flag}  {action.get('description', '')}")
    return 0


def command_run(config, args):
    workload = config.workload(args.workload)
    action = config.action(workload, args.action)
    argv = config.argv(action["command"], action.get("node"))
    if action.get("confirm") and not args.yes:
        try:
            answer = input(f"Run {workload['name']}/{action['name']} on {action.get('node', 'this machine')}? [y/N] ")
        except EOFError:  # no terminal to answer: never act
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("cancelled")
            return 1
    return subprocess.run(argv).returncode


class Runner:
    """Runs one action at a time in the background and keeps its output."""

    def __init__(self):
        self.lines = collections.deque(maxlen=2000)
        self.process = None
        self.title = ""
        self.lock = threading.Lock()

    @property
    def busy(self):
        return self.process is not None and self.process.poll() is None

    def start(self, title, argv):
        if self.busy:
            return False
        with self.lock:
            self.lines.clear()
            self.title = title
            self.lines.append(f"$ {shlex.join(argv)}")
        self.process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        stdin=subprocess.DEVNULL, bufsize=1)
        threading.Thread(target=self._read, args=(self.process,), daemon=True).start()
        return True

    def _read(self, process):
        for line in process.stdout:
            with self.lock:
                self.lines.append(line.rstrip("\n"))
        code = process.wait()
        with self.lock:
            self.lines.append(f"[exit {code} at {datetime.datetime.now():%H:%M:%S}]")

    def stop(self):
        if self.busy:
            self.process.terminate()


ESCAPES = {"A": curses.KEY_UP, "B": curses.KEY_DOWN, "5~": curses.KEY_PPAGE, "6~": curses.KEY_NPAGE}


def read_key(window, delay=-1):
    """getch, with ESC [ x and ESC O x arrow/page sequences decoded even when the
    terminal's sequences differ from terminfo (tmux, some SSH clients). A lone
    ESC is returned as 27. ``delay`` is the window's timeout to restore (-1 blocks)."""
    key = window.getch()
    if key != 27:
        return key
    window.timeout(0)
    try:
        sequence = ""
        for _ in range(3):
            following = window.getch()
            if following == -1:
                break
            sequence += chr(following)
            if sequence[0] not in "[O" or sequence[1:] in ESCAPES:
                break
    finally:
        window.timeout(delay)
    return ESCAPES.get(sequence[1:], 27) if sequence[:1] in ("[", "O") else 27


class TUI:
    def __init__(self, screen, config):
        self.screen, self.config = screen, config
        self.nodes = [{"ok": False, "error": "probing..."} for _ in config.nodes]
        self.health = [None for _ in config.workloads]
        self.updated = None
        self.focus = "workloads" if config.workloads else "nodes"
        self.row = {"nodes": 0, "workloads": next((i for i, w in enumerate(config.workloads) if w.get("default")), 0)}
        self.runner = Runner()
        self.scroll = 0
        self.message = ""
        self.paused = False
        threading.Thread(target=self._refresh_loop, daemon=True).start()

    def refresh_now(self):
        self.nodes, self.health = snapshot(self.config)
        self.updated = datetime.datetime.now()

    def _refresh_loop(self):
        while True:
            if not self.paused:
                self.refresh_now()
            time.sleep(self.config.refresh)

    def add(self, y, x, text, attr=0):
        height, width = self.screen.getmaxyx()
        if 0 <= y < height and x < width:
            self.screen.addnstr(y, x, text, max(0, width - x - 1), attr)

    def draw(self):
        screen = self.screen
        screen.erase()
        height, width = screen.getmaxyx()
        updated = f"{self.updated:%H:%M:%S}" if self.updated else "..."
        state = "paused" if self.paused else f"every {self.config.refresh:g}s"
        self.add(0, 0, f" {self.config.name}  |  refreshed {updated} ({state})  |  {self.config.path.name} ".ljust(width),
                 curses.color_pair(1) | curses.A_BOLD)
        y = 2
        self.add(y, 0, "NODES", curses.A_BOLD | (curses.A_UNDERLINE if self.focus == "nodes" else 0))
        for i, (node, state) in enumerate(zip(self.config.nodes, self.nodes)):
            y += 1
            selected = self.focus == "nodes" and self.row["nodes"] == i
            colour = curses.color_pair(2 if state.get("ok") else 3)
            self.add(y, 1, ("> " if selected else "  ") + node_row(self.config, node, state),
                     colour | (curses.A_REVERSE if selected else 0))
        y += 2
        self.add(y, 0, "WORKLOADS", curses.A_BOLD | (curses.A_UNDERLINE if self.focus == "workloads" else 0))
        for i, (workload, status) in enumerate(zip(self.config.workloads, self.health)):
            y += 1
            selected = self.focus == "workloads" and self.row["workloads"] == i
            colour = curses.color_pair(2 if status == 200 else 4 if status is None else 3)
            text = (f"{workload['name']:<12} {health_text(status):<8} {workload.get('api', ''):<34} "
                    f"{workload.get('description', '')}")
            self.add(y, 1, ("> " if selected else "  ") + text, colour | (curses.A_REVERSE if selected else 0))
        y += 2
        title = self.runner.title or "output"
        running = "  (running; k to stop)" if self.runner.busy else ""
        self.add(y, 0, f"OUTPUT: {title}{running}", curses.A_BOLD)
        top = y + 1
        rows = max(1, height - top - 2)
        with self.runner.lock:
            lines = list(self.runner.lines)
        end = max(0, len(lines) - self.scroll)
        for offset, line in enumerate(lines[max(0, end - rows):end]):
            self.add(top + offset, 1, line)
        footer = (" ↑↓ select  Tab nodes/workloads  Enter actions  r refresh  p pause  "
                  "PgUp/PgDn scroll  k stop action  q quit ")
        self.add(height - 1, 0, (self.message or footer).ljust(width), curses.color_pair(1))
        screen.refresh()

    def choose(self, title, options):
        """A centred menu; returns the chosen index or None."""
        height, width = self.screen.getmaxyx()
        w = min(width - 4, max(len(title), *(len(o) for o in options)) + 6)
        h = min(height - 2, len(options) + 4)
        window = curses.newwin(h, w, max(0, (height - h) // 2), max(0, (width - w) // 2))
        window.keypad(True)
        index = 0
        while True:
            window.erase()
            window.box()
            window.addnstr(0, 2, f" {title} ", w - 4, curses.A_BOLD)
            for i, option in enumerate(options[: h - 4]):
                window.addnstr(i + 2, 2, option, w - 4, curses.A_REVERSE if i == index else 0)
            window.refresh()
            key = read_key(window)
            if key in (curses.KEY_UP, ord("k")):
                index = (index - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord("j")):
                index = (index + 1) % len(options)
            elif key in (10, 13, curses.KEY_ENTER):
                return index
            elif key in (27, ord("q")):
                return None

    def confirm(self, text):
        return self.choose(text, ["No", "Yes"]) == 1

    def open_actions(self):
        if self.runner.busy:
            self.message = " an action is still running; k stops it "
            return
        if self.focus == "workloads" and self.config.workloads:
            workload = self.config.workloads[self.row["workloads"]]
            actions = workload.get("actions", [])
            labels = [f"{a['name']}  [{a.get('node', 'local')}]" + ("  !" if a.get("confirm") else "")
                      for a in actions]
            title = workload["name"]
            node_name = None
        else:
            node = self.config.nodes[self.row["nodes"]]
            actions = self.config.node_actions
            labels = [a["name"] for a in actions]
            title = node["name"]
            node_name = node["name"]
        if not actions:
            self.message = " no actions configured "
            return
        choice = self.choose(title, labels)
        if choice is None:
            return
        action = actions[choice]
        if action.get("confirm") and not self.confirm(f"Run {title}/{action['name']}?"):
            return
        target = node_name or action.get("node")
        self.scroll = 0
        self.runner.start(f"{title} / {action['name']}", self.config.argv(action["command"], target))

    def loop(self):
        curses.curs_set(0)
        if hasattr(curses, "set_escdelay"):
            curses.set_escdelay(25)
        curses.start_color()
        curses.use_default_colors()
        for pair, colour in ((1, curses.COLOR_CYAN), (2, curses.COLOR_GREEN), (3, curses.COLOR_RED),
                             (4, curses.COLOR_YELLOW)):
            curses.init_pair(pair, colour if pair > 1 else curses.COLOR_BLACK, -1 if pair > 1 else curses.COLOR_CYAN)
        self.screen.timeout(250)
        self.screen.keypad(True)
        while True:
            self.draw()
            key = read_key(self.screen, 250)
            if key == -1:
                continue
            self.message = ""
            panel = self.focus
            count = len(self.config.nodes if panel == "nodes" else self.config.workloads)
            if key == ord("q"):
                if not self.runner.busy or self.confirm("An action is running. Quit anyway?"):
                    return
            elif key == 9:  # Tab
                self.focus = "workloads" if panel == "nodes" and self.config.workloads else "nodes"
            elif key == curses.KEY_UP:
                self.row[panel] = (self.row[panel] - 1) % max(1, count)
            elif key == curses.KEY_DOWN:
                self.row[panel] = (self.row[panel] + 1) % max(1, count)
            elif key in (10, 13, curses.KEY_ENTER):
                self.open_actions()
            elif key == ord("r"):
                threading.Thread(target=self.refresh_now, daemon=True).start()
                self.message = " refreshing... "
            elif key == ord("p"):
                self.paused = not self.paused
            elif key == ord("k"):
                self.runner.stop()
            elif key == curses.KEY_PPAGE:
                self.scroll += 10
            elif key == curses.KEY_NPAGE:
                self.scroll = max(0, self.scroll - 10)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("CLUSTER_CONFIG", DEFAULT_CONFIG)))
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("tui")
    sub.add_parser("status")
    sub.add_parser("list")
    run = sub.add_parser("run")
    run.add_argument("workload")
    run.add_argument("action")
    run.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()
    config = Config(args.config)
    if args.command in (None, "tui"):
        if not sys.stdout.isatty():
            return command_status(config, args)
        curses.wrapper(lambda screen: TUI(screen, config).loop())
        # Leave at once: in-flight SSH probes run in pool threads that interpreter
        # shutdown would otherwise wait for (up to the 15 s probe timeout).
        sys.stdout.flush()
        os._exit(0)
    return {"status": command_status, "list": command_list, "run": command_run}[args.command](config, args)


if __name__ == "__main__":
    raise SystemExit(main())
