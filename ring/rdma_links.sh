#!/usr/bin/env bash
# RDMA write bandwidth on each ring cable and plane. Rank i f0 -> rank i+1 f1.
R=(spark-r0 spark-r1 gx10-r1 gx10-r0)
for i in 0 1 2 3; do
  a=${R[$i]}; b=${R[$(( (i+1)%4 ))]}
  for pl in "10.10:rocep1s0f0:rocep1s0f1" "10.11:roceP2p1s0f0:roceP2p1s0f1"; do
    IFS=: read net d0 d1 <<< "$pl"; port=$((18500+i))
    ssh $b "timeout 30 ib_write_bw -d $d1 -x 3 -F -q 4 -s 1048576 -D 3 -p $port >/dev/null 2>&1" & sleep 2
    bw=$(ssh $a "timeout 30 ib_write_bw -d $d0 -x 3 -F -q 4 -s 1048576 -D 3 -p $port $net.$i.11 2>&1" | awk '/^ 1048576/{print $4" MB/s"}')
    wait
    echo "cable $i $net: $a/$d0 -> $b/$d1 : ${bw:-FAILED}"
  done
done
