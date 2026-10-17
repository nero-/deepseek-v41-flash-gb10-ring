"""Exercise DS41-width BF16 prefill under the pinned upstream contention harness."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / 'upstream/flashinfer'))
import torch
from b12x.gemm import bf16_gemv
from b12x.preparation import PreparationSession, PreparedCall
from tests.experimental.b12x.race.noise import SMContention
from tests.experimental.b12x.race.replay import ReplayCheck

torch.manual_seed(415122)
device = torch.device('cuda', 0)
contention = SMContention(device)
source = torch.randn(4096, 5120, device=device).bfloat16()
weight = (torch.randn(384, 5120, device=device) / 5120**0.5).bfloat16()
output = torch.empty(4096, 384, device=device, dtype=torch.float32)
session = PreparationSession(device=device, autotune=False, compile_workers=2)
plan = bf16_gemv.plan(bf16_gemv.query_from_call(source, weight, out=output),
                     override=bf16_gemv.GemvConfig(backend='prefill'))
session.prepare((plan.request(name='ds41.bf16_prefill', prepare_call=lambda state:
    PreparedCall(run=lambda: state.run(source, weight, out=output), output=output)),))
session.freeze()
def forward():
    bf16_gemv.mm(source, weight, out=output, plan=plan)
forward()
torch.cuda.synchronize()
expected = source.double() @ weight.double().T
torch.testing.assert_close(output.double(), expected, atol=1e-6, rtol=1e-6)
check = ReplayCheck(forward, {'output':output}, reset=lambda: output.fill_(float('nan')))
with contention:
    report = check.run(replays=5000, contention=contention)
assert report.replays == 5000 and report.noise_kernels > 0 and report.bad == 0, report
Path('/receipts/bf16-contention.json').write_text(json.dumps(asdict(report), indent=2) + '\n')
print(report, flush=True)
session.close()
