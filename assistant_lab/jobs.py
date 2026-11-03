"""Durable, local task submission. GUI lifetime is independent of workers."""
from pathlib import Path
from datetime import datetime
import json,os,subprocess,sys,time,uuid
from .config import STATE_ROOT,ROOT,GUI_PYTHON,RECON_PYTHON,SAM3_PYTHON,RECON,FINETUNE
from .protocol import validate_settings

COMPUTE_ACTIONS={'inspect_data','reconstruct','find_center','analyze','try_center','try_angle','segment','prepare_dataset','train','resume_training'}

def atomic_json(path,data):
    path=Path(path);temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2),encoding='utf-8')
    for attempt in range(50):
        try:temp.replace(path);return
        except PermissionError:
            if attempt==49:raise
            time.sleep(.02)

def read_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default if default is not None else {}

def validate_job(action,s):
    if action not in COMPUTE_ACTIONS:raise ValueError('Not a supported background task')
    validate_settings(s)
    if not s.get('output_root','').strip():raise ValueError('Choose an output folder')
    if action in ('reconstruct','find_center','analyze','try_center','try_angle'):
        if not s['input_hdf5'] or not Path(s['input_hdf5']).is_file():raise ValueError('Select an existing HDF5 file')
        if not RECON_PYTHON.is_file() or not (RECON/'backend_runner.py').is_file():raise ValueError('Reconstruction runtime/project is missing')
        if action=='reconstruct' and s['center']<=0:raise ValueError('Enter a known center, or use Find Center first')
        if action in ('find_center','analyze') and s['geometry']!='tomography':raise ValueError('Automatic center search currently supports tomography')
        if action=='try_angle' and s['center']<=0:raise ValueError('Enter the fixed rotation center before trying lamino angles')
        if s['geometry']=='laminography' and s['method'] not in ('fourierrec','linerec'):raise ValueError('Laminography supports FourierRec or LineRec')
    if action in ('segment','find_center','analyze','train','resume_training'):
        if not s['checkpoint'] or not Path(s['checkpoint']).is_file():raise ValueError('Select the SAM3 checkpoint')
    if action in ('segment','find_center','analyze'):
        if not s['prompt'].strip():raise ValueError('Enter a SAM3 prompt')
        if not SAM3_PYTHON.is_file():raise ValueError('SAM3 Python runtime is missing')
    if action=='segment' and (not s['image_folder'] or not Path(s['image_folder']).is_dir()):raise ValueError('Select an image folder')
    if action in ('prepare_dataset','train','resume_training'):
        if not s['dataset'] or not Path(s['dataset']).exists():raise ValueError('Select a COCO source / saved train-validation dataset')
        if not (FINETUNE/'finetune_gui/training.py').is_file():raise ValueError('Fine-tune project is missing')
    if action=='resume_training' and (not s['resume_checkpoint'] or not Path(s['resume_checkpoint']).is_file()):raise ValueError('Select a full Resume checkpoint')

def process_alive(pid):
    if not pid:return False
    if os.name!='nt':
        try:os.kill(pid,0);return True
        except OSError:return False
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.windll.kernel32;kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,int(pid))
    if not handle:return False
    try:
        code=wintypes.DWORD();return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
    finally:kernel.CloseHandle(handle)

class JobStore:
    def __init__(self,root=None):self.root=Path(root or STATE_ROOT/'test_outputs/jobs');self.root.mkdir(parents=True,exist_ok=True);self._children=[]
    def list_jobs(self):
        jobs=[]
        for path in sorted(self.root.glob('*/job.json'),reverse=True):
            config=read_json(path);status=read_json(path.parent/'job_status.json')
            if not config:continue
            jobs.append({**config,**status,'job_dir':str(path.parent)})
        return jobs
    def active(self):
        for job in self.list_jobs():
            if job.get('state') in ('queued','running','stopping'):
                if process_alive(job.get('worker_pid')):return job
                path=Path(job['job_dir'])/'job_status.json'
                atomic_json(path,{**job,'state':'failed','phase':'Worker exited without a final result','error':'Inspect the task log; partial outputs were retained.'})
        return None
    def submit(self,action,settings,plan=None):
        validate_job(action,settings)
        if self.active():raise ValueError('A task is already active; wait for completion or use Safe Stop')
        folder=self.root/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid.uuid4().hex[:8]+'_'+action)
        folder.mkdir(exist_ok=False)
        config=dict(id=folder.name,action=action,settings=settings,submitted_at=datetime.now().isoformat(),
                    plan=plan or {},job_dir=str(folder))
        atomic_json(folder/'job.json',config)
        log=(folder/'worker.log').open('w',encoding='utf-8')
        argv=[str(GUI_PYTHON),str(ROOT/'worker.py'),'--job',str(folder/'job.json')]
        flags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0
        env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1'}
        for key in ('PYTHONPATH','PYTHONHOME'):env.pop(key,None)
        try:child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,creationflags=flags,env=env)
        except Exception as error:
            atomic_json(folder/'job_status.json',dict(state='failed',phase='Cannot launch worker',error=str(error)));raise
        finally:log.close()
        self._children.append(child)
        config['worker_pid']=child.pid;atomic_json(folder/'job.json',config)
        return config
    def stop(self,job):
        folder=Path(job['job_dir']).resolve()
        if folder.parent!=self.root.resolve() or not (folder/'job.json').is_file():raise ValueError('Not an owned task')
        (folder/'CANCEL').touch()
    def last(self):
        rows=self.list_jobs();return rows[0] if rows else None
