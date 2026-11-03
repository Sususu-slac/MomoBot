"""Download selected external weights, pinned by revision, length and SHA256."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,json,hashlib,math,os,time,urllib.request
root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'model_catalog.json').read_text(encoding='utf-8'))
p=argparse.ArgumentParser();p.add_argument('--model',choices=[e['id'] for e in catalog['models']]);p.add_argument('--all',action='store_true');p.add_argument('--model-dir',type=Path,default=Path(os.environ.get('BL62_MODEL_DIR','D:/Chcekpoints/LLM')));a=p.parse_args()
for entry in catalog['models']:
 if not a.all and entry['id']!=(a.model or catalog['default']):continue
 a.model_dir.mkdir(parents=True,exist_ok=True);path=a.model_dir/entry['filename'];size=entry['bytes'];sha=entry['sha256']
 if Path(entry['filename']).name!=entry['filename']:raise ValueError('Invalid catalog filename')
 verified=path.with_suffix('.verified.json')
 if path.exists() and verified.exists():
  try:
   if path.stat().st_size==size and json.loads(verified.read_text(encoding='utf-8')).get('sha256')==sha:print(entry['id']+': already verified',flush=True);continue
  except (OSError,ValueError):pass
 parts=a.model_dir/('.'+entry['id']+'-download');parts.mkdir(exist_ok=True);block=128*1024**2;count=math.ceil(size/block)
 url='https://huggingface.co/'+entry['repo']+'/resolve/'+entry['revision']+'/'+entry['filename']+'?download=true'
 def get(index):
  expected=min(block,size-index*block);done=parts/f'{index:04d}.bin';partial=parts/f'{index:04d}.part'
  if done.exists() and done.stat().st_size==expected:return
  for attempt in range(8):
   n=partial.stat().st_size if partial.exists() else 0
   if n==expected:partial.replace(done);return
   start=index*block+n;end=index*block+expected-1
   try:
    req=urllib.request.Request(url+'&part='+str(index),headers={'Range':f'bytes={start}-{end}'})
    with urllib.request.urlopen(req,timeout=45) as response:
     if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{size}':raise RuntimeError('Range mismatch')
     with partial.open('ab') as f:
      for data in iter(lambda:response.read(4*1024**2),b''):f.write(data)
    if partial.stat().st_size!=expected:raise RuntimeError('Incomplete range')
    partial.replace(done);return
   except Exception:
    if attempt==7:raise
    time.sleep(min(2**attempt,15))
 with ThreadPoolExecutor(max_workers=8) as pool:
  tasks=[pool.submit(get,i) for i in range(count)]
  while not all(f.done() for f in tasks):
   for f in tasks:
    if f.done() and f.exception():raise f.exception()
   n=0
   for part in parts.iterdir():
    try:n+=part.stat().st_size
    except FileNotFoundError:pass
   print(f'{entry["id"]}: {100*n/size:.1f}% ({n/1e9:.2f}/{size/1e9:.2f} GB)',flush=True);time.sleep(15)
  for f in tasks:f.result()
 assembled=path.with_suffix('.assembling');digest=hashlib.sha256()
 with assembled.open('wb') as out:
  for index in range(count):
   with (parts/f'{index:04d}.bin').open('rb') as f:
    for data in iter(lambda:f.read(16*1024**2),b''):out.write(data);digest.update(data)
 if assembled.stat().st_size!=size or digest.hexdigest()!=sha:raise RuntimeError('Checksum mismatch; model not activated')
 assembled.replace(path);verified.write_text(json.dumps({**entry,'verified':True},indent=2),encoding='utf-8')
 for part in parts.glob('*.bin'):part.unlink()
 parts.rmdir();print(entry['id']+': downloaded and SHA256 verified',flush=True)
