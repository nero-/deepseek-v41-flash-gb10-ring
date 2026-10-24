#!/usr/bin/env python3
"""Remove retired Docker containers and images from the four nodes (2026-10-24).

Keeps the running selection, the B12X rollback (image 9f26f0b3718c and the
ds41-before-tilelang-rN containers) and the October 17 switched-baseline
fallback (image a182696cb59f and ds41-before-switch-baseline-rN). The two
rollback images get stable tags first, because their current tags belong to
retired campaigns. Removes only named containers and the exact image IDs and
tags listed here; no prune, no force. Writes a before/after manifest.
"""
import datetime
import json
import os
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESULTS.parents[1] / "scripts"))
import fleet  # noqa: E402

DRY = os.environ.get("DRY_RUN") == "1"
CURRENT = "sha256:2fc5565e9c15b005f3297a552131b8973a2f19fb811868a8358a3e99b33491d0"
KEEP_IMAGES = {
    "9f26f0b3718c": "ds41-b12x-rollback:20261021",
    "a182696cb59f": "ds41-b12x-switch-baseline:20261017",
    CURRENT[7:19]: "ds41f-tilelang:19f2c20ed4d6-1022-sparkring",
}
KEEP_CONTAINERS = ("ds41-optimized-r{rank}", "ds41-before-tilelang-r{rank}", "ds41-before-switch-baseline-r{rank}")
# Image repositories that belong only to retired work.
RETIRED_REPOSITORIES = ("ds41-flare-prepare", "ds41-live-cost", "ds41-draft-tau", "ds41-moe-backport",
                        "ds41-live-cost-parent", "ds41-draft-tau-parent", "ds41-rocenante-switch",
                        "dsv41-sparkring", "dsv41-switch-parent", "glm53-ring", "glm53-trellismx",
                        "ghcr.io/miaai-lab/glm-5.3-flash-exl3-2x-dgx-sparks-tensorfold")


def inventory(rank):
    containers = [dict(zip(("name", "id", "image", "state"), line.split("\t"))) for line in fleet.remote(
        rank, ["docker", "ps", "-a", "--no-trunc", "--format", "{{.Names}}\t{{.ID}}\t{{.Image}}\t{{.State}}"]
    ).stdout.splitlines()]
    for c in containers:
        c["image_id"] = json.loads(fleet.remote(rank, ["docker", "inspect", "--format", "{{json .Image}}", c["id"]]).stdout)
    images = [dict(zip(("tag", "id", "size"), line.split("\t"))) for line in fleet.remote(
        rank, ["docker", "images", "--no-trunc", "--format", "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}"]
    ).stdout.splitlines()]
    disk = fleet.remote(rank, ["df", "-B1", "--output=used,avail", "/var/lib/docker"]).stdout.split()[-2:]
    return {"containers": containers, "images": images, "disk_used_bytes": int(disk[0]), "disk_avail_bytes": int(disk[1])}


def mutate(rank, argv):
    if DRY:
        print(f"[dry-run] rank {rank}: {' '.join(argv)}")
        return type("R", (), {"returncode": 0, "stderr": ""})()
    return fleet.remote(rank, argv, check=False)


def clean(rank):
    before = inventory(rank)
    keep_names = {name.format(rank=rank) for name in KEEP_CONTAINERS}
    log = []
    for short, tag in KEEP_IMAGES.items():
        if any(i["id"][7:19] == short for i in before["images"]):
            r = mutate(rank, ["docker", "tag", f"sha256:{next(i['id'][7:] for i in before['images'] if i['id'][7:19] == short)}", tag])
            log.append({"tag": tag, "returncode": r.returncode, "stderr": r.stderr.strip()})
    removed_containers, used_images = [], set()
    for c in before["containers"]:
        if c["name"] in keep_names:
            continue
        assert c["state"] != "running", f"rank {rank}: {c['name']} is running"
        r = mutate(rank, ["docker", "rm", c["name"]])
        removed_containers.append({**c, "returncode": r.returncode, "stderr": r.stderr.strip()})
        used_images.add(c["image_id"])
    keep_ids = {i["id"] for i in before["images"] if i["id"][7:19] in KEEP_IMAGES}
    removed_tags = []
    for image in before["images"]:
        repository = image["tag"].rsplit(":", 1)[0]
        if repository in RETIRED_REPOSITORIES:
            r = mutate(rank, ["docker", "rmi", image["tag"] if not image["tag"].endswith(":<none>") else image["id"]])
            removed_tags.append({**image, "returncode": r.returncode, "stderr": r.stderr.strip()[-300:]})
    # Image IDs that only the removed containers referenced (untagged leftovers), never a kept image.
    removed_ids = []
    remaining = {i["id"] for i in inventory(rank)["images"]}
    for image_id in sorted(used_images - keep_ids):
        if image_id in remaining or not image_id:
            continue
        r = mutate(rank, ["docker", "image", "rm", image_id])
        removed_ids.append({"id": image_id, "returncode": r.returncode, "stderr": r.stderr.strip()[-300:]})
    if DRY:
        return {"rank": rank, "dry_run": True}
    after = inventory(rank)
    kept = {c["name"] for c in after["containers"]}
    assert f"ds41-optimized-r{rank}" in kept and f"ds41-before-tilelang-r{rank}" in kept, kept
    assert any(i["id"] == CURRENT for i in after["images"])
    return {"rank": rank, "before": before, "tags_added": log, "removed_containers": removed_containers,
            "removed_image_tags": removed_tags, "removed_untagged_images": removed_ids, "after": after,
            "freed_bytes": before["disk_used_bytes"] - after["disk_used_bytes"]}


results = fleet.parallel(clean)
if DRY:
    raise SystemExit(0)
receipt = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "keep_images": KEEP_IMAGES,
           "keep_containers": KEEP_CONTAINERS, "nodes": results}
(RESULTS / "fleet-cleanup.json").write_text(json.dumps(receipt, indent=2) + "\n")
for r in results:
    failed = [x for x in r["removed_containers"] + r["removed_image_tags"] + r["removed_untagged_images"] if x["returncode"]]
    print(f"rank {r['rank']}: removed {len(r['removed_containers'])} containers, {len(r['removed_image_tags'])} tags, "
          f"{len(r['removed_untagged_images'])} untagged images; freed {r['freed_bytes'] / 2**30:.1f} GiB; "
          f"left {len(r['after']['containers'])} containers / {len(r['after']['images'])} images; failures {len(failed)}")
    for x in failed:
        print("   ", x.get("name") or x.get("tag") or x.get("id"), x["stderr"][:200])
