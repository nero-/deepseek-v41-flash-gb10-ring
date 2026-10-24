"""Shared helpers for the spark-ds41f TileLang trial (adapted from the
October 21 reboot retest so evidence has the same shape)."""
import concurrent.futures, datetime, hashlib, json, re, shlex, subprocess
from pathlib import Path

TRIAL = Path(__file__).resolve().parents[1]
RESULTS = TRIAL / 'results/20261024-trial'
REPO = TRIAL.parent / 'deepseek-v41-flash-spark'
PRODUCTION_IMAGE = 'sha256:9f26f0b3718ccca889cfd93cb72e2165b6d4c11dd9dc93fe65f585883537f2db'
SELECTION = 'c87a397ccc4614c6f3fee59e566bb7599e7165c80e858bb12c84d78ef5e27775'
HOSTS = ('192.168.50.219', '192.168.50.129', '192.168.50.192', '192.168.50.23')
ALIASES = ('spark-r0', 'spark-r1', 'gx10-r1', 'gx10-r0')
RAIL_A = ('10.10.10.1', '10.10.10.2', '10.10.10.4', '10.10.10.3')
TRIAL_CONTAINER = 'ds41f-tilelang-r{rank}'
KERNEL_EVENTS = r'out of memory|oom-kill|killed process|NVRM|Xid|page allocation failure'


def remote(rank, command, data=None, check=True, timeout=30):
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=4', '-o', 'ServerAliveInterval=5',
                        '-o', 'ServerAliveCountMax=3', '-o', 'HostName=' + HOSTS[rank], '-o', 'ProxyCommand=none',
                        ALIASES[rank], shlex.join(command)], input=data, text=True, capture_output=True,
                       timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f'rank {rank}: {command[:3]}: {r.stderr[-2000:]}')
    return r


def parallel(fn):
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        return list(pool.map(fn, range(4)))


def save(name, value):
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / name).open('x') as f:
        json.dump({'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), **value}, f, indent=2)
        f.write('\n')


def sha_selected():
    return hashlib.sha256(remote(0, ['cat', '/etc/deepseek-ring/optimized-specs.json']).stdout.encode()).hexdigest()


def host_snapshot(rank):
    code = """import json,pathlib,subprocess,os
def run(*args):
 p=subprocess.run(args,text=True,capture_output=True);return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
m={l.split()[0].rstrip(':'):int(l.split()[1]) for l in pathlib.Path('/proc/meminfo').read_text().splitlines()}
print(json.dumps({'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'uptime':pathlib.Path('/proc/uptime').read_text().strip(),'kernel':os.uname().release,'used_gib':(m['MemTotal']-m['MemAvailable'])/1024**2,'available_gib':m['MemAvailable']/1024**2,'swap_used_gib':(m['SwapTotal']-m['SwapFree'])/1024**2,'clock':run('systemctl','show','gb10-gpu-clock-cap.service','-p','ActiveState','-p','UnitFileState','-p','ExecStart'),'running_containers':run('docker','ps','--format','{{.Names}} {{.Image}}')}))
"""
    return {'rank': rank, **json.loads(remote(rank, ['python3', '-c', code]).stdout)}


def kernels(since, name):
    def one(rank):
        r = remote(rank, ['journalctl', '-k', '--since', '@' + str(int(since)), '--no-pager'])
        return {'rank': rank, 'events': [x for x in r.stdout.splitlines() if re.search(KERNEL_EVENTS, x, re.I)],
                'stdout': r.stdout}
    rows = parallel(one)
    save(name, {'since_epoch': since, 'nodes': rows})
    return rows
