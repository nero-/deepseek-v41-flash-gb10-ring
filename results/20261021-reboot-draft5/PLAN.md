# Five-draft reboot and three-run retest

Authorized by the user on October 21 UTC after the low five-draft screen.
One coordinated reboot of all four nodes, followed by three matched focused
screens on one fresh serving startup. This tests repeatability after a reboot;
it is not three independent boots or a randomized causal reboot experiment.

Preserve the installed c87a397c... five-draft selection, immutable 9f26f0b... image,
20 GiB KV, stock 1017 weights, port 8015, default thinking, temperature/top_p 1,
full vocabulary, switched fabric and persistent 0-2350 MHz ceiling. Preserve the
exact stopped qualified four-draft containers and root selection backup.
No CSF, model rebuild, driver/kernel change, or broader tuning campaign.

1. Record boot IDs, selection/image/container identities, memory and kernel logs.
2. Stop all model ranks and disable mesh supervisors; verify empty GPU/Docker
   workload and disabled legacy services before graceful host reboots.
3. Verify changed boot IDs, all-node SSH, clock persistence and switched fabric.
4. Monitor startup memory, SSH responsiveness and kernel events; start through
   the installed controller. Run API, loaded-clock and cold-retrieval checks.
5. Require responsive SSH/API, no OOM kill/Xid and no post-ready allocation
   events before timed tests. Startup-only warnings remain a qualification
   limitation even if subsequent tests can proceed. Stop the monitor before
   benchmarks; collect kernel/memory receipts between runs, not during them.
6. Run unmodified LIL 0.7.6 three times: 8K/32K, C1/C8/C16, 20-second cells,
   max 2048 tokens, default thinking, temperature 1, no hardware monitor/resume,
   plus five separate coding probes per run. Preserve every attempt and flags.
7. Report individual results, median and range against the previous five-draft
   screen and nearby four-draft control. Verify final serving identity/health.

Historical reports stay unchanged. This folder contains the new receipts and
an addendum; any improvement is limited to the measured configuration/workload.
