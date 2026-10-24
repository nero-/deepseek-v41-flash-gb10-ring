#!/usr/bin/env python3
"""Render the spark-ds41f-1022 TP4 launch for the switched SparkRing fleet.

spark-ds41f's own launcher rejects a four-node switched fabric (its topology
check allows only ring transports at four nodes), so this script loads the
pinned checkout's bin/spark, resolves its promoted ``tp4-ring`` recipe exactly
as that launcher does, and then applies one explicit, recorded site overlay:

* fabric: sparknet's documented switched clique (``SPARKNET_ROCE_TOPOLOGY=direct``
  with no peer map, both port-1 rails) and sparknet's ``switched`` NCCL profile
  in place of the ring-only NCCL policy;
* bootstrap on the rail-A addresses, as the qualified vLLM selection does;
* port 8015 and model name ``DeepSeek-V4.1-Flash-TP4`` so existing clients and
  the LIL protocol run unchanged;
* our local 1017 checkpoint and a fresh trial cache, read-only weights;
* the production SparkRing seccomp profile in place of ``seccomp=unconfined``.

Model arithmetic, kernels, sizing, speculation and every other recipe value
are left as rendered. Writes one argv per rank plus a manifest; performs no
SSH or Docker action.
"""
import argparse
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

# The pinned spark-ds41f checkout prepared by `bin/spark build prepare`.
DEFAULT_CHECKOUT = Path.home() / "Agent/Builds/DS41-ds41f-tilelang/build/spark-ds41f"
CHECKOUT = DEFAULT_CHECKOUT
PINNED_COMMIT = "9f1565f060ad84a6f06a745a9b7b4191393cc842"
SHAPE = "tp4-ring"

CHECKPOINT = ("/srv/sparkring/sparkring/checkpoints/deepseek-ai--DeepSeek-V4.1-Flash-1017/"
              "1bae0e1088993b9b82de08f59de5be5a34e42170")
CACHE = "/srv/sparkring/sparkring/cache/ds41f-tilelang-20261024"
SECCOMP = "/home/nero/ds41f-tilelang-20261024/seccomp.json"
PORT = "8015"
MODEL_NAME = "DeepSeek-V4.1-Flash-TP4"
CONTAINER = "ds41f-tilelang-r{rank}"
MASTER_ADDR = "10.10.10.1"
RAILS = "rocep1s0f1,roceP2p1s0f1"
SOCKET_IFNAME = "enp1s0f1np1"

# Rank order is fixed by OPERATIONS.md: never reorder the two GX10 ranks.
NODES = [
    {"name": "spark-r0", "rank": 0, "head": True, "management_ip": "192.168.50.219", "rail_a": "10.10.10.1"},
    {"name": "spark-r1", "rank": 1, "head": False, "management_ip": "192.168.50.129", "rail_a": "10.10.10.2"},
    {"name": "gx10-r1", "rank": 2, "head": False, "management_ip": "192.168.50.192", "rail_a": "10.10.10.4"},
    {"name": "gx10-r0", "rank": 3, "head": False, "management_ip": "192.168.50.23", "rail_a": "10.10.10.3"},
]

# Ring-only settings the switched clique must not carry: forced Ring algorithm,
# the patched NCCL's switchless bidirectional rings, and the ring's channel and
# connection policy. sparknet's switched profile replaces them below.
RING_ONLY = (
    "NCCL_ALGO", "NCCL_SWITCHLESS_BIDIRECTIONAL", "NCCL_MIN_NCHANNELS", "NCCL_MIN_TRAFFIC_PER_CHANNEL",
    "NCCL_RUNTIME_CONNECT", "NCCL_CUMEM_HOST_ENABLE", "NCCL_GIN_ENABLE", "NCCL_MNNVL_ENABLE",
    "NCCL_PAT_ENABLE", "NCCL_RMA_DISABLE", "NCCL_COLLNET_ENABLE", "NCCL_IB_SUBNET_PREFIX_LEN",
    "NCCL_THREAD_THRESHOLDS", "SPARKNET_ROCE_PEER_HCAS",
)

# Site values that differ from sparknet's switched profile, with the reason.
SITE_ENVIRONMENT = {
    # Rails A and B are separate /24s on one CRS812 bridge; the qualified vLLM
    # selection keeps NCCL on matching rails.
    "NCCL_CROSS_NIC": "0",
    "NCCL_IB_HCA": "=" + RAILS,
    "NCCL_IB_GID_INDEX": "3",
    "NCCL_SOCKET_IFNAME": SOCKET_IFNAME,
    "GLOO_SOCKET_IFNAME": SOCKET_IFNAME,
    "TP_SOCKET_IFNAME": SOCKET_IFNAME,
    "SPARKNET_ROCE_TOPOLOGY": "direct",
    "SPARKNET_ROCE_HCA": RAILS,
    "SPARKNET_ROCE_GID_INDEX": "3",
    # The pinned Dockerfile (after spark-ds41f #486) installs the patched sources
    # under /opt/spark-ds41f; the recipe still names the pre-rename /opt/spark3,
    # which would silently fall back to the base image's stock vLLM. This is the
    # image's own ENV value.
    "PYTHONPATH": "/opt/spark-ds41f/candidate/vllm:/opt/spark-ds41f/candidate/b12x",
}
# Serving limits that follow the SparkRing deployment policy rather than the
# recipe: production's 20 GiB KV per rank (sized to the head's ~118 GiB startup
# budget) and the full-request image ceiling of 999 (four caused HTTP 400 on
# the fifth image of a conversation; OPERATIONS.md, Images and chat history).
SERVE_OVERRIDES = {
    "--kv-cache-memory-bytes": "21474836480",
    "--limit-mm-per-prompt": '{"image":999}',
}

# QoS/PFC/ECN are not configured on the CRS812 (OPERATIONS.md); the qualified
# RoCEnante path leaves the traffic class at its default, so this trial does too.
OMIT_FROM_SWITCHED_PROFILE = ("NCCL_IB_TC", "SPARKNET_ROCE_TRAFFIC_CLASS")


def load_spark():
    loader = importlib.machinery.SourceFileLoader("spark_cli", str(CHECKOUT / "bin/spark"))
    spec = importlib.util.spec_from_loader("spark_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def switched_profile() -> dict:
    path = CHECKOUT / ".work/build"
    sources = sorted(path.glob("*/src/sparknet/recipes/switched.json"))
    if len(sources) != 1:
        raise SystemExit(f"expected one prepared sparknet switched recipe under {path}, found {len(sources)}")
    return json.loads(sources[0].read_text())


def replace_argument(args: list, flag: str, value: str) -> None:
    if args.count(flag) != 1:
        raise SystemExit(f"expected exactly one {flag} in the rendered command")
    args[args.index(flag) + 1] = value


def site_cluster(spark, recipe_cluster: dict) -> tuple[dict, list[str]]:
    cluster = copy.deepcopy(recipe_cluster)
    changes = []
    profile = switched_profile()
    if profile["transport"] != "oneshot-switched":
        raise SystemExit("sparknet's switched recipe changed transport")

    cluster["fabric"] = {"transport": "oneshot-direct"}
    changes.append("fabric: oneshot-ring4 -> sparknet switched clique (topology direct, no peer map)")
    env = cluster["environment"]
    for key in RING_ONLY:
        if key in env:
            changes.append(f"env: removed ring-only {key}={env.pop(key)}")
    for key, value in profile["common_environment"].items():
        if key in OMIT_FROM_SWITCHED_PROFILE:
            continue
        if env.get(key) != value:
            changes.append(f"env: {key} {env.get(key)!r} -> {value!r} (sparknet switched profile)")
        env[key] = value
    for key, value in SITE_ENVIRONMENT.items():
        if env.get(key) != value:
            changes.append(f"env: {key} {env.get(key)!r} -> {value!r} (site)")
        env[key] = value

    cluster["distributed"]["master_addr"] = MASTER_ADDR
    changes.append(f"bootstrap: master_addr -> {MASTER_ADDR} (rail A, as the qualified selection)")
    args = cluster["serve_args"]
    replace_argument(args, "--port", PORT)
    replace_argument(args, "--served-model-name", MODEL_NAME)
    changes.append(f"api: port 8000 -> {PORT}, model name -> {MODEL_NAME}")
    for flag, value in SERVE_OVERRIDES.items():
        before = args[args.index(flag) + 1]
        replace_argument(args, flag, value)
        changes.append(f"serving: {flag} {before} -> {value} (SparkRing policy)")

    container = cluster["container"]
    container["name"] = CONTAINER
    mounts = container["mounts"]
    hub = [m for m in mounts if m[1] == "/hub"]
    served = args[0]
    if len(hub) != 1 or not served.startswith("/hub/"):
        raise SystemExit("expected the recipe's hub-mounted 1017 model profile")
    container["mounts"] = [[CHECKPOINT, served, "ro"]] + [
        [CACHE if m[1] == "/cache" else m[0], m[1], m[2]] for m in mounts if m[1] != "/hub"]
    changes.append(f"mounts: local 1017 checkpoint at {served} (ro); cache {CACHE}")
    run_args = container["docker_run_args"]
    if run_args.count("--security-opt=seccomp=unconfined") != 1:
        raise SystemExit("expected the recipe's unconfined seccomp setting")
    run_args[run_args.index("--security-opt=seccomp=unconfined")] = f"--security-opt=seccomp={SECCOMP}"
    changes.append("security: seccomp=unconfined -> production SparkRing seccomp profile (includes io_uring)")
    return cluster, changes


def argv_for(spark, cluster: dict, node: dict, image: str) -> list[str]:
    view = copy.deepcopy(cluster)
    view["container"]["name"] = CONTAINER.format(rank=node["rank"])
    view["container"]["image"] = image
    rendered = spark.rendered_docker_command(view, {**node, "roce_peer_hcas": {}})
    env_at = [i for i, a in enumerate(rendered) if a == "--env"]
    env = dict(rendered[i + 1].split("=", 1) for i in env_at)
    if "SPARKNET_ROCE_PEER_HCAS" in env:
        # sparknet's direct mode treats a present map as explicit routes; the
        # switched clique is the no-map path.
        index = rendered.index(f"SPARKNET_ROCE_PEER_HCAS={env['SPARKNET_ROCE_PEER_HCAS']}")
        del rendered[index - 1:index + 1]
    index = rendered.index(f"VLLM_HOST_IP={node['management_ip']}")
    rendered[index] = f"VLLM_HOST_IP={node['rail_a']}"
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="image ID (sha256:...) every rank must run")
    parser.add_argument("--output", required=True, help="new directory for the rendered launch")
    parser.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT, help="pinned spark-ds41f checkout")
    args = parser.parse_args()
    global CHECKOUT
    CHECKOUT = args.checkout.resolve()
    if not args.image.startswith("sha256:") or len(args.image) != 71:
        raise SystemExit("--image must be a full sha256 image ID")
    head = (CHECKOUT / ".git/HEAD").read_text().strip()
    if head != PINNED_COMMIT:
        raise SystemExit(f"checkout is at {head}, expected {PINNED_COMMIT}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)

    sys.argv = [sys.argv[0]]
    spark = load_spark()
    recipe_cluster = spark.read_cluster("config/cluster.json", SHAPE)
    if recipe_cluster["fabric"]["transport"] != "oneshot-ring4":
        raise SystemExit("the pinned tp4-ring shape changed transport")
    cluster, changes = site_cluster(spark, recipe_cluster)

    ranks = []
    for node in NODES:
        argv = argv_for(spark, cluster, node, args.image)
        path = output / f"rank{node['rank']}.json"
        path.write_text(json.dumps(argv, indent=1) + "\n")
        ranks.append({"rank": node["rank"], "host": node["name"], "container": CONTAINER.format(rank=node["rank"]),
                      "argv_sha256": hashlib.sha256(json.dumps(argv).encode()).hexdigest(), "path": path.name})
    manifest = {
        "source": {"repository": "https://github.com/christopherowen/spark-ds41f", "commit": PINNED_COMMIT,
                   "promoted_baseline": recipe_cluster.get("promoted_baseline"), "shape": SHAPE,
                   "expected_labels": recipe_cluster["container"]["expected_labels"],
                   "recipe_image_tag": recipe_cluster["container"]["image"]},
        "image": args.image,
        "start_order": [n["rank"] for n in NODES if not n["head"]] + [0],
        "site_changes": changes,
        "unchanged": "kernels, arithmetic, sizing, speculation, scheduler, sampling and all other recipe values",
        "ranks": ranks,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("\n".join(changes))
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
