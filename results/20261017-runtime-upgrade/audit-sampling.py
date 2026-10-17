import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/Users/jg/Agent/Builds/deepseek-v41-flash-ring/scripts')
from fleet import remote
spec=json.loads((ROOT/'candidate-specs.json').read_text())['specs'][0]
command=spec['command'];override=json.loads(command[command.index('--override-generation-config')+1])
code=r'''import json,sys,pathlib,types
from vllm.transformers_utils.config import try_get_generation_config
from vllm.config.model import ModelConfig
from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
p=pathlib.Path('/models/target');assert not (p/'generation_config.json').exists()
gen=try_get_generation_config(str(p),trust_remote_code=False)
diff=gen.to_diff_dict() if gen else {}
obj=types.SimpleNamespace(generation_config='auto',try_get_generation_config=lambda:dict(diff),override_generation_config=json.loads(sys.argv[1]))
defaults=ModelConfig.get_diff_sampling_param(obj)
assert 'max_tokens' not in defaults
fields=['temperature','top_p','top_k','min_p','repetition_penalty','presence_penalty','frequency_penalty','max_tokens']
rows={}
for name,extra in [('omitted',{}),('client_p095',{'top_p':0.95})]:
 request=ChatCompletionRequest(model='DeepSeek-V4.1-Flash-TP4',messages=[{'role':'user','content':'Hello'}],**extra)
 params=request.to_sampling_params(max_tokens=1048000,default_sampling_params=defaults)
 rows[name]={k:getattr(params,k) for k in fields}
assert rows['omitted']==dict(temperature=1.0,top_p=1.0,top_k=-1,min_p=0.0,repetition_penalty=1.0,presence_penalty=0.0,frequency_penalty=0.0,max_tokens=1048000),rows
assert rows['client_p095']['top_p']==0.95
print('SAMPLING_AUDIT_JSON='+json.dumps({'checkpoint_generation_config_present':False,'hf_generation_diff':diff,'server_defaults':defaults,'request_conversion':rows,'output_cap_note':'No max_new_tokens/default max_tokens in model generation defaults; request/context remaining capacity still governs output.'}))
'''
r=remote(0,['docker','exec',spec['name'],'python3','-c',code,json.dumps(override)])
(ROOT/'sampling-audit-candidate.log').write_text(r.stdout+r.stderr)
line=next(x for x in r.stdout.splitlines() if x.startswith('SAMPLING_AUDIT_JSON='))
record=json.loads(line.split('=',1)[1]);(ROOT/'sampling-audit-candidate.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
