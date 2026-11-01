"""Resumable range download of the pinned model; activate only after SHA256."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,math,os,time,urllib.request
path=Path('D:/Chcekpoints/LLM/Qwen3.8-27B-Q4_K_M.gguf') if os.name=='nt' else Path('/mnt/d/Chcekpoints/LLM/Qwen3.8-27B-Q4_K_M.gguf')
size=18973870528;sha='c600de0300ae8a0eb3a6c0b8b5561b8b96f16bd2c863c2a66c42de29d391a747';revision='a316ea527fde32c12487be7574e2db5ac2ad2a7e'
url='https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/resolve/'+revision+'/Qwen3.8-27B-Q4_K_M.gguf?download=true'
block=128*1024**2;count=math.ceil(size/block);parts=path.parent/'.Qwen3.8-27B-download';parts.mkdir(exist_ok=True);prefix=path.with_suffix(path.suffix+'.part');began=time.monotonic()
if prefix.exists():
 with prefix.open('rb') as source:
  for index in range(math.ceil(prefix.stat().st_size/block)):
   data=source.read(block);expected=min(block,size-index*block);target=parts/f'{index:04d}.bin' if len(data)==expected else parts/f'{index:04d}.part'
   if (parts/f'{index:04d}.bin').exists():continue
   if not target.exists() or target.stat().st_size<len(data):target.write_bytes(data)
def get(index):
 expected=min(block,size-index*block);complete=parts/f'{index:04d}.bin';partial=parts/f'{index:04d}.part'
 if complete.exists() and complete.stat().st_size==expected:return
 for attempt in range(8):
  n=partial.stat().st_size if partial.exists() else 0
  if n==expected:partial.replace(complete);return
  start=index*block+n;end=index*block+expected-1
  try:
   request=urllib.request.Request(url+'&part='+str(index),headers={'Range':f'bytes={start}-{end}'})
   with urllib.request.urlopen(request,timeout=45) as response:
    if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{size}':raise RuntimeError('Server range response mismatch')
    with partial.open('ab') as out:
     while True:
      data=response.read(4*1024**2)
      if not data:break
      out.write(data)
   if partial.stat().st_size!=expected:raise RuntimeError('Incomplete range')
   partial.replace(complete);return
  except Exception as error:
   if attempt==7:raise
   time.sleep(min(2**attempt,15))
with ThreadPoolExecutor(max_workers=8) as pool:
 futures=[pool.submit(get,i) for i in range(count)]
 while not all(f.done() for f in futures):
  for f in futures:
   if f.done() and f.exception():raise f.exception()
  downloaded=0
  for item in parts.iterdir():
   try:downloaded+=item.stat().st_size
   except FileNotFoundError:pass  # A worker just renamed a completed range.
  elapsed=time.monotonic()-began
  print(json.dumps({'phase':'parallel download','percent':round(downloaded/size*100,2),'GB':round(downloaded/1e9,3),'elapsed_s':round(elapsed),'workers':8}),flush=True);time.sleep(20)
 for f in futures:f.result()
print(json.dumps({'phase':'assemble and SHA256'}),flush=True);target=path.with_suffix('.assembling');h=hashlib.sha256()
with target.open('wb') as out:
 for index in range(count):
  with (parts/f'{index:04d}.bin').open('rb') as source:
   for data in iter(lambda:source.read(16*1024**2),b''):out.write(data);h.update(data)
if target.stat().st_size!=size or h.hexdigest()!=sha:raise RuntimeError('Model checksum mismatch; not activated.')
target.replace(path)
report={'model':str(path),'bytes':size,'sha256':sha,'revision':revision,'seconds':round(time.monotonic()-began,2)};path.with_suffix('.verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
# Only delete this downloader's verified duplicate scratch data.
for item in parts.iterdir():item.unlink()
parts.rmdir()
if prefix.exists():prefix.unlink()
