#!/usr/bin/env python3
"""Run on the head after stopping serving; normalize installed fabric profiles."""
import shlex
import subprocess

CODE = """
import subprocess
from pathlib import Path
for base in Path('/sys/class/infiniband').iterdir():
    for nic in (base/'device/net').iterdir():
        dev = nic.name
        con = subprocess.check_output(['nmcli', '-g', 'GENERAL.CONNECTION', 'device', 'show', dev], text=True).strip()
        if not con.startswith('sparkring-'):
            raise RuntimeError(con)
        subprocess.run(['nmcli', 'connection', 'modify', con, 'ipv6.addr-gen-mode', 'eui64'], check=True)
        subprocess.run(['nmcli', 'connection', 'up', con], check=True, stdout=subprocess.DEVNULL)
print('Normalized fabric IPv6 generation to EUI-64.')
"""

for host in ['spark-r0', 'spark-r1', 'gx10-r1', 'gx10-r0']:
    subprocess.run(['ssh', host, 'sudo -n python3 -c ' + shlex.quote(CODE)], check=True)
