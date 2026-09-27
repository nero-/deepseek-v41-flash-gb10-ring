#!/usr/bin/env bash
# One experiment: overrides on top of .env.tp4.prod, reboot, smoke, qeval + LIL quick.
#   bench/experiment.sh NAME [KEY=VAL ...]         (from the Mac; CASES=quick by default)
set -uo pipefail
NAME=$1; shift
H=spark-r0 D='~/NewModels/DS4.1'
scp -q "$(dirname "$0")/env_override.py" $H:/tmp/env_override.py
ssh -n $H "cd $D && python3 /tmp/env_override.py .env.tp4.prod .env.tp4 $(printf "'%s' " "$@") && ./start-tp4.sh stop >/dev/null 2>&1; ./start-tp4.sh serve 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > ~/NewModels/serve-$NAME.out; tail -2 ~/NewModels/serve-$NAME.out"
ssh -n $H "grep -E 'max_total_num_tokens=' $D/logs-tp4/dsv41.log | tail -1 | grep -o 'max_total_num_tokens=[0-9]*'"
ssh -n gx10-r0 "python3 ~/bench/smoke.py | tail -1 && RING_ARGS='${RING_ARGS:-}' bash ~/bench/evalrun.sh $NAME ${CASES:-quick}"
