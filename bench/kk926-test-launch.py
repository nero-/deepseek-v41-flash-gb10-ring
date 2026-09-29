"""Run GPU regression tests with the serving image's exact toolchain environment."""
import importlib.util,json,os,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('tc','/opt/sparkring/toolchain/toolchain.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
env=m.configure_environment(json.loads((m.ROOT/'toolchain.json').read_text()),os.environ)
env['PYTHONPATH']=env.get('PYTHONPATH','')+':/tests/deps';env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1';env['VLLM_PLUGINS']=''
os.execve(sys.executable,[sys.executable,*sys.argv[1:]],env)
