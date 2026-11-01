from __future__ import annotations
import json,time,urllib.request,urllib.error,socket,subprocess,os,threading,secrets
from pathlib import Path
from .config import ROOT,MODEL,RUNTIME_ROOT
from .protocol import SYSTEM,SCHEMA,parse_plan,Plan

def post_json(url,payload,timeout=180,token=''):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:return json.load(response)
    except urllib.error.HTTPError as error:raise RuntimeError(f'Local model HTTP {error.code}: '+error.read().decode(errors='replace')[:1500]) from error

class LocalModel:
    def __init__(self):self.process=None;self.port=None;self.mode='CPU';self.log=None;self.started=0.;self.ready_seconds=None;self.token=''
    @property
    def base_url(self):return f'http://127.0.0.1:{self.port}'
    @property
    def running(self):return self.process is not None and self.process.poll() is None
    def start(self,mode='GPU 1',threads=8,context=8192,model_path=MODEL):
        if self.running:return
        model_path=Path(model_path)
        if not model_path.is_file():raise FileNotFoundError('Model file not found: '+str(model_path))
        runtime=RUNTIME_ROOT/('cpu' if mode=='CPU' else 'cuda')
        candidates=list(runtime.rglob('llama-server.exe'))
        if not candidates:raise FileNotFoundError('llama-server.exe not found under '+str(runtime))
        self.mode=mode;self.token=secrets.token_urlsafe(24)
        if self.log:self.log.close()
        with socket.socket() as socket_:socket_.bind(('127.0.0.1',0));self.port=socket_.getsockname()[1]
        log_dir=ROOT/'test_outputs/model_logs';log_dir.mkdir(parents=True,exist_ok=True)
        self.log_path=log_dir/f'llama_{time.time_ns()}.log';self.log=self.log_path.open('w',encoding='utf-8')
        args=[str(candidates[0]),'-m',str(model_path),'--host','127.0.0.1','--port',str(self.port),
              '-c',str(context),'-t',str(threads),'-tb',str(threads),'-np','1','-ngl','0' if mode=='CPU' else '99',
              '--jinja','--reasoning','off','--reasoning-budget','0','--no-reasoning-preserve','--batch-size','512','--ubatch-size','128',
              '--no-context-shift','--metrics','--api-key',self.token]
        env=dict(os.environ);env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
        if mode!='CPU':env['CUDA_VISIBLE_DEVICES']=mode.split()[-1];env['CUDA_DEVICE_ORDER']='PCI_BUS_ID'
        else:env['CUDA_VISIBLE_DEVICES']=''
        self.started=time.perf_counter();self.ready_seconds=None
        self.process=subprocess.Popen(args,cwd=str(candidates[0].parent),env=env,stdout=self.log,stderr=subprocess.STDOUT,
            **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
    def healthy(self):
        if not self.running:return False
        try:
            request=urllib.request.Request(self.base_url+'/health',headers={'Authorization':'Bearer '+self.token})
            with urllib.request.urlopen(request,timeout=.3) as response:good=response.status==200
            if good and self.ready_seconds is None:self.ready_seconds=time.perf_counter()-self.started
            return good
        except (OSError,ValueError):return False
    def wait_ready(self,timeout=180):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.healthy():return
            if not self.running:
                tail=self.log_path.read_text(encoding='utf-8',errors='replace')[-3000:]
                raise RuntimeError('Local model exited:\n'+tail)
            time.sleep(.2)
        raise TimeoutError('Local model did not become ready; see '+str(self.log_path))
    def interpret(self,text,settings,last_job=None):
        context={k:v for k,v in settings.items() if k not in ('training_template','training_python','training_repo','sam3_repo')}
        message='Current settings: '+json.dumps(context)+'\nLast task: '+json.dumps(last_job or {})+'\nUser command: '+text
        began=time.perf_counter()
        rendered=post_json(self.base_url+'/apply-template',{'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':message}]},token=self.token)
        response=post_json(self.base_url+'/completion',dict(prompt=rendered['prompt'],temperature=0,seed=42,n_predict=320,cache_prompt=True,json_schema=SCHEMA),token=self.token)
        raw=response['content']
        if response.get('stopped_limit'):raise RuntimeError('Model response was truncated; no task was accepted')
        validation_notice=None
        try:plan=parse_plan(raw)
        except Exception as error:
            debug=ROOT/'test_outputs/model_errors';debug.mkdir(parents=True,exist_ok=True)
            (debug/f'{time.time_ns()}.json').write_text(json.dumps(response,indent=2),encoding='utf-8')
            if str(error).startswith('Select one Task GPU'):
                validation_notice=str(error);plan=Plan('clarify',{},'This test GUI trains on one GPU. Please choose GPU 0 or GPU 1.')
            else:raise ValueError(str(error)+': '+raw[:900]) from error
        # Paths may only come from the user's explicit text, never be copied from a different context field.
        normalized=text.replace('\\','/').casefold()
        for field,value in plan.updates.items():
            if field in ('input_hdf5','image_folder','dataset','checkpoint','resume_checkpoint') and value.replace('\\','/').casefold() not in normalized:
                raise ValueError('Model supplied an unspecified path. Select the path in the GUI or include it in the command.')
        original={pair['field']:pair['value'] for pair in json.loads(raw).get('updates',[]) if isinstance(pair,dict) and 'field' in pair and 'value' in pair}
        normalized_fields=[]
        if 'method' in plan.updates and original.get('method')!=plan.updates['method']:normalized_fields.append({'field':'method','before':original.get('method'),'after':plan.updates['method']})
        return plan,dict(seconds=time.perf_counter()-began,usage=response.get('usage',{}),timings=response.get('timings',{}),mode=self.mode,raw=raw,validation_notice=validation_notice,normalized_fields=normalized_fields)
    def stop(self):
        if self.running:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        if self.log:self.log.close();self.log=None
        self.process=None

def process_memory_mib(pid):
    if not pid:return None
    try:
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),('PeakWorkingSetSize',ctypes.c_size_t),
                      ('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
                      ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
        kernel=ctypes.windll.kernel32;kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        handle=kernel.OpenProcess(0x410,False,pid)
        if not handle:return None
        try:
            values=Counters();values.cb=ctypes.sizeof(values)
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle,ctypes.byref(values),values.cb):return values.WorkingSetSize/2**20
        finally:kernel.CloseHandle(handle)
    except Exception:return None
