#!/usr/bin/env bash
# RDMA latency over every hardware-forwarded opposite-node path of the dsv41 mesh.
# Each node has two /32 routes (one per plane, via different neighbours) to its opposite
# node. perftest's TCP control channel uses the LAN address (Docker's FORWARD policy is
# DROP, and the mesh forwards RDMA in NIC hardware only); both ends set flow label 16383
# so the marker tags them for the neighbour's hairpin rule.
declare -A LAN=([spark-r0]=192.168.50.219 [spark-r1]=192.168.50.129 [gx10-r1]=192.168.50.192 [gx10-r0]=192.168.50.23)
declare -A OPP=([spark-r0]=gx10-r1 [gx10-r1]=spark-r0 [spark-r1]=gx10-r0 [gx10-r0]=spark-r1)
port=18700
for src in spark-r0 spark-r1 gx10-r1 gx10-r0; do
  dst=${OPP[$src]}
  while read -r ip dev; do
    sdev=$(ssh -n $src "ls /sys/class/net/$dev/device/infiniband")
    ddev=$(ssh -n $dst "for n in /sys/class/net/en*; do ip -4 -br addr show \${n##*/} | grep -q \"$ip/\" && ls \$n/device/infiniband; done")
    port=$((port+1))
    ssh -n $dst "timeout 40 ib_write_lat -d $ddev -x 3 -s 61440 -n 3000 -F -p $port --flow_label=16383 >/dev/null 2>&1" & sleep 2
    r=$(ssh -n $src "timeout 30 ib_write_lat -d $sdev -x 3 -s 61440 -n 3000 -F -p $port --flow_label=16383 ${LAN[$dst]} 2>&1" | awk '/^ *61440/{print $6" us avg"}')
    wait
    printf '%-8s %-13s -> %-8s %-13s %-11s %s\n' $src $sdev $dst $ddev $ip "${r:-FAILED}"
  done < <(ssh $src "ip -4 route show | awk '\$1 ~ /^10\.1[01]\.[0-9]+\.[0-9]+\$/ {print \$1, \$5}'")
done
