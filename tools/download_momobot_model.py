"""Download the pinned public model, resume partial data and verify before use."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--destination',required=True);args=p.parse_args()
path=Path(args.destination);path.parent.mkdir(parents=True,exist_ok=True)
size=18973870528;sha='c600de0300ae8a0eb3a6c0b8b5561b8b96f16bd2c863c2a66c42de29d391a747'
url='https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/resolve/a316ea527fde32c12487be7574e2db5ac2ad2a7e/Qwen3.8-27B-Q4_K_M.gguf?download=true'
part=path.with_suffix(path.suffix+'.part');start=time.monotonic()
if not path.exists():
 cmd=['curl','-f','-L','--retry','8','--retry-all-errors','--retry-delay','3','--connect-timeout','20','--continue-at','-','--silent','--show-error','--output',str(part),url]
 proc=subprocess.Popen(cmd)
 while proc.poll() is None:
  n=part.stat().st_size if part.exists() else 0
  print(json.dumps({'phase':'download','percent':round(n/size*100,2),'GB':round(n/1e9,3),'elapsed_s':round(time.monotonic()-start)}),flush=True);time.sleep(20)
 if proc.returncode:raise SystemExit(proc.returncode)
 target=part
else:target=path
if target.stat().st_size!=size:raise RuntimeError('Downloaded size does not match the published model.')
print(json.dumps({'phase':'sha256','GB':size/1e9}),flush=True)
h=hashlib.sha256()
with target.open('rb') as f:
 for chunk in iter(lambda:f.read(16*1024**2),b''):h.update(chunk)
if h.hexdigest()!=sha:raise RuntimeError('SHA256 mismatch; the partial file was kept, never activated.')
if target!=path:part.replace(path)
report={'model':str(path),'bytes':size,'sha256':sha,'revision':'a316ea527fde32c12487be7574e2db5ac2ad2a7e','seconds':round(time.monotonic()-start,2)}
path.with_suffix('.verified.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
