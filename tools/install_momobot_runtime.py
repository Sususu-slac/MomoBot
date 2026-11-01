"""Install a pinned llama.cpp Windows runtime into the project only."""
from pathlib import Path
import hashlib,json,subprocess,urllib.request,zipfile
from concurrent.futures import ThreadPoolExecutor
root=Path(__file__).resolve().parents[1];tag='b11988'
with urllib.request.urlopen('https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/'+tag,timeout=30) as r:release=json.load(r)
selected={f'llama-{tag}-bin-win-cuda-12.4-x64.zip':'cuda','cudart-llama-bin-win-cuda-12.4-x64.zip':'cuda',f'llama-{tag}-bin-win-cpu-x64.zip':'cpu'}
cache=root/'runtime/downloads';cache.mkdir(parents=True,exist_ok=True)
assets=[a for a in release['assets'] if a['name'] in selected]
if len(assets)!=len(selected):raise RuntimeError('Expected runtime archives are missing.')
def fetch(a):
 path=cache/a['name'];part=path.with_suffix('.zip.part')
 if not path.exists():
  subprocess.run(['curl','-f','-L','--retry','5','--retry-all-errors','--connect-timeout','20','--continue-at','-','--silent','--show-error','--output',str(part),a['browser_download_url']],check=True)
  if part.stat().st_size!=a['size']:raise RuntimeError('Archive size mismatch: '+a['name'])
  part.replace(path)
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 if a.get('digest') and a['digest']!='sha256:'+digest:raise RuntimeError('Archive digest mismatch: '+a['name'])
 print(json.dumps({'downloaded':a['name'],'bytes':a['size'],'sha256':digest}),flush=True)
 return a,path,digest
with ThreadPoolExecutor(max_workers=3) as pool:downloads=list(pool.map(fetch,assets))
report=[]
for a,path,digest in downloads:
 target=root/'runtime'/('llama-'+tag)/selected[a['name']];target.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(path) as z:
  for member in z.infolist():
   rel=Path(member.filename)
   if rel.is_absolute() or '..' in rel.parts:raise RuntimeError('Unexpected archive path')
  if z.testzip():raise RuntimeError('Archive CRC error')
  z.extractall(target)
 report.append({'archive':a['name'],'bytes':a['size'],'sha256':digest,'url':a['browser_download_url']})
(root/'runtime'/('llama-'+tag)/'verified.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'installed':str(root/'runtime'/('llama-'+tag)),'servers':[str(p.relative_to(root)) for p in (root/'runtime'/('llama-'+tag)).rglob('llama-server.exe')]}),flush=True)
