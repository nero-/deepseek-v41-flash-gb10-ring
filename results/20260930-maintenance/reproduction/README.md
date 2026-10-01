# Execution snapshots

These are the campaign scripts used from `/tmp` on the operator Mac, retained
for audit alongside command/status receipts. They use fixed fleet addresses,
local paths and a dated results directory. They are not an idempotent installer
or instructions to rerun completed upgrades/reboots. `spark-maintenance-resume.py`
checks existing systemd jobs before starting package operations. The reboot
script shown here includes the kernel assertion added after the first reboot
exposed the obsolete GRUB pin. The corresponding first-attempt receipts remain.

Administrative commands use existing passwordless sudo on the GX10s and the
already-authorized Docker host administration access on the Sparks. No sudoers
or SSH permission changes were made. Root backups remain private on the hosts.
