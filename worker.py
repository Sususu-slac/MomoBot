"""Owns one job and its children, independent of the chat window."""
from __future__ import annotations
from pathlib import Path
import argparse,json,os,sys,time,subprocess,traceback,shlex
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from assistant_lab.config import RECON,FINETUNE,RECON_PYTHON,SAM3_PYTHON
from assistant_lab.jobs import atomic_json,read_json,validate_job

class Cancelled(Exception):pass

def wsl(path):
    raw=str(path).replace('\\','/')
    if len(raw)>2 and raw[1:3]==':/':return '/mnt/'+raw[0].lower()+raw[2:]
    if raw.startswith('//wsl.localhost/') or raw.startswith('//wsl$/'):return '/'+ '/'.join(raw.split('/')[4:])
    return raw

class Worker:
    def __init__(self,path):
        self.config=read_json(path);self.folder=Path(path).parent;self.s=self.config['settings'];self.action=self.config['action']
        self.output=self.folder/'results';self.output.mkdir(exist_ok=True);self.started=time.monotonic();self.child=None
        self.status=dict(state='running',phase='Preparing task',completed=0,total=0,output=str(self.output),worker_pid=os.getpid());self.signals_sent=set()
    def emit(self,**values):
        self.status.update(values);self.status['elapsed_seconds']=time.monotonic()-self.started
        atomic_json(self.folder/'job_status.json',self.status)
    def check(self):
        if (self.folder/'CANCEL').exists():raise Cancelled()
    def run_child(self,args,phase,progress=None,training=False):
        self.check();self.emit(phase=phase,completed=0,total=0)
        log_path=self.folder/'backend.log'
        env=dict(os.environ)
        for key in ('PYTHONPATH','PYTHONHOME','CUDA_VISIBLE_DEVICES'):env.pop(key,None)
        env.update(PYTHONNOUSERSITE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        with log_path.open('a',encoding='utf-8') as log:
            print('RUN',json.dumps(args),flush=True)
            self.child=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT,
                **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
            self.emit(child_pid=self.child.pid)
            try:
                stop_sent=False;stop_started=0
                while self.child.poll() is None:
                    cancelled=(self.folder/'CANCEL').exists()
                    if cancelled and not stop_sent:
                        self.emit(state='stopping',phase='Stopping this task safely');stop_sent=True;stop_started=time.monotonic()
                        if training:
                            (self.output/'stop_requested').touch()
                            self.signal_training()
                        else:
                            sys.path.insert(0,str(RECON));from ct_recon_gui.process_utils import terminate_tree
                            terminate_tree(self.child.pid)
                    if cancelled and training:
                        # The pid file may appear after Stop was requested during environment startup.
                        self.signal_training()
                    if cancelled and training and time.monotonic()-stop_started>90:
                        self.signal_training(force=True)
                    if progress and not cancelled:
                        try:progress()
                        except (OSError,ValueError):pass
                    else:self.emit()
                    time.sleep(.4)
                self.check()
                if self.child.returncode:
                    tail=log_path.read_text(encoding='utf-8',errors='replace')[-3500:]
                    raise RuntimeError(f'Backend exited {self.child.returncode}:\n'+tail)
            finally:
                if self.child.poll() is None:
                    if training:self.signal_training(force=True)
                    sys.path.insert(0,str(RECON));from ct_recon_gui.process_utils import terminate_tree
                    terminate_tree(self.child.pid)
    def signal_training(self,force=False):
        pid=(self.output/'training.pid')
        if not pid.is_file():return
        value=pid.read_text().strip()
        if not value.isdigit():return
        ready=self.output/'training.signal_ready'
        if not force and (not ready.is_file() or ready.read_text().strip()!=value):return
        identity=(value,force)
        if identity in self.signals_sent:return
        signal='KILL' if force else 'INT'
        helper=ROOT/'assistant_lab/wsl_signal.py'
        result=subprocess.run(['C:/Windows/System32/wsl.exe','-d',self.s['distro'],'--exec',self.s['training_python'],wsl(helper),value,self.folder.name,signal],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode==0:self.signals_sent.add(identity)
    def inspect(self):
        result={}
        if self.s['input_hdf5']:
            script='import sys,json,dataclasses;sys.path.insert(0,sys.argv[1]);from ct_recon_gui.hdf5_inspector import inspect_hdf5;d=dataclasses.asdict(inspect_hdf5(sys.argv[2]));d["path"]=str(d["path"]);print(json.dumps(d))'
            self.run_child([str(RECON_PYTHON),'-c',script,str(RECON),self.s['input_hdf5']],'Inspecting HDF5 metadata')
            text=(self.folder/'backend.log').read_text(encoding='utf-8',errors='replace')
            result['hdf5']=json.loads(text.strip().splitlines()[-1])
        if self.s['image_folder']:
            files=self.images();result['images']=dict(folder=self.s['image_folder'],available=len(files))
        atomic_json(self.output/'inspection.json',result);return result
    def reconstruct(self):
        s=self.s
        code='import sys;sys.path.insert(0,sys.argv[1]);from ct_recon_gui.hdf5_inspector import inspect_hdf5;i=inspect_hdf5(sys.argv[2]);assert 0<=int(sys.argv[3])<int(sys.argv[4])<=i.data_shape[1],"Row range outside detector";assert 0<float(sys.argv[5])<i.data_shape[2],"Center outside detector"'
        self.run_child([str(RECON_PYTHON),'-c',code,str(RECON),s['input_hdf5'],str(s['start_row']),str(s['end_row']),str(s['center'])],'Checking detector geometry')
        method=('lamino_'+s['method']) if s['geometry']=='laminography' else s['method']
        folder=self.output/'reconstruction';folder.mkdir()
        args=[str(RECON_PYTHON),str(RECON/'backend_runner.py'),method,s['input_hdf5'],str(folder),
              '--reconstruction-type','full','--start-row',str(s['start_row']),'--end-row',str(s['end_row']),
              '--center',str(s['center']),'--gpu',str(s['gpu']),'--binning',str(s['binning']),
              '--chunk-size',str(s['chunk_size']),'--nsino-per-chunk',str(s['chunk_size']),
              '--iterations',str(s['iterations']),'--lamino-angle',str(s['lamino_angle'])]
        if s['method']=='lprec':args.append('--accept-uniform-angle-approximation')
        total=(s['end_row']-s['start_row'])//(2**s['binning'])
        def progress():self.emit(completed=len(list(folder.rglob('*.tiff'))),total=total)
        self.run_child(args,'Reconstructing selected rows',progress)
        files=list(folder.rglob('*.tiff'))
        if len(files)!=total:raise RuntimeError(f'Expected {total} slices, found {len(files)}')
        # Confirm actual numeric output, not only a zero return code.
        verify='import sys,tifffile,numpy as np;a=tifffile.imread(sys.argv[1]);assert a.ndim==2 and np.isfinite(a).all() and np.ptp(a)>0;print("VERIFIED",a.shape,a.dtype)'
        self.run_child([str(RECON_PYTHON),'-c',verify,str(files[len(files)//2])],'Verifying reconstruction')
        return dict(slices=len(files),folder=str(folder),center=s['center'],binning=s['binning'])
    def images(self):
        folder=Path(self.s['image_folder'])
        if not folder.is_dir():raise ValueError('Image folder does not exist')
        files=sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.png','.tif','.tiff','.jpg','.jpeg','.bmp'))
        if not files:raise ValueError('No supported images in the folder')
        return files
    def trial(self):
        import h5py
        s=self.s
        with h5py.File(s['input_hdf5'],'r') as handle:_,rows,width=handle['exchange/data'].shape
        row=s.get('trial_row') if s.get('trial_row') is not None else rows//2
        if not 0<=row<rows:raise ValueError('Trial row is outside the detector')
        angle=self.action=='try_angle';lamino=angle or s['geometry']=='laminography'
        center=s['center'] or (width-1)/2
        method='lamino_linerec' if lamino else s['method']
        if not lamino and method not in ('fourierrec','linerec','lprec'):raise ValueError('Trial reconstruction uses FourierRec, LineRec or LpRec')
        folder=self.output/'trial_reconstructions';folder.mkdir()
        args=[str(RECON_PYTHON),str(RECON/'backend_runner.py'),method,s['input_hdf5'],str(folder),
              '--reconstruction-type','try','--search-kind','angle' if angle else 'center',
              '--start-row','0','--end-row',str(rows),'--try-row',str(row),'--center',str(center),
              '--gpu',str(s['gpu']),'--binning',str(s['binning']),'--chunk-size',str(s['chunk_size']),
              '--lamino-angle',str(s['lamino_angle']),
              '--lamino-search-width' if angle else '--center-search-width',str(s.get('trial_width',2 if angle else 10)),
              '--lamino-search-step' if angle else '--center-search-step',str(s.get('trial_step',.25 if angle else 1))]
        if method=='lprec':args.append('--accept-uniform-angle-approximation')
        def progress():self.emit(completed=len(list(folder.rglob('*.tiff'))),total=0)
        self.run_child(args,'Generating angle candidates on one slice' if angle else 'Generating center candidates on one slice',progress)
        files=list(folder.rglob('*.tiff'))
        if len(files)<2:raise RuntimeError('Trial search did not produce at least two candidate TIFFs; increase the width or reduce the step')
        verify='import sys,tifffile,numpy as np;a=tifffile.imread(sys.argv[1]);assert a.ndim==2 and np.isfinite(a).all() and np.ptp(a)>0;print("VERIFIED_CANDIDATE",a.shape)'
        self.run_child([str(RECON_PYTHON),'-c',verify,str(files[len(files)//2])],'Verifying candidate images')
        result=dict(folder=str(folder),candidates=len(files),trial_row=row,search_kind='angle' if angle else 'center',
                    anchor=s['lamino_angle'] if angle else center,half_width=s['trial_width'],step=s['trial_step'],
                    selection='User selects the best candidate; no automatic scoring was performed',files=[str(p) for p in files])
        atomic_json(folder/'trial_manifest.json',result);return result
    def sam_config(self):
        s=self.s
        cfg={**s,'output':str(self.output),'input':s['input_hdf5'],'repo':s['sam3_repo'],
             'recon_python':str(RECON_PYTHON),'sam3_python':str(SAM3_PYTHON),'search_method':'fourierrec','refresh_seconds':3}
        atomic_json(self.folder/'sam_job.json',cfg);return self.folder/'sam_job.json'
    def sam(self):
        cfg_path=self.sam_config()
        if self.action=='segment':
            files=self.images();n=self.s['max_images'];files=files[:n] if n else files
            atomic_json(self.folder/'image_manifest.json',[str(p) for p in files])
        def progress():
            status=read_json(self.output/'status.json')
            if status:self.emit(phase=status.get('detail') or status.get('stage','SAM3'),completed=status.get('completed',0),total=status.get('total',0),backend_status=status)
        self.run_child([str(SAM3_PYTHON),str(ROOT/'worker.py'),'--sam-engine',self.action,'--config',str(cfg_path)],'Starting SAM3 backend',progress)
        summary=read_json(self.output/'analysis_summary.json') if self.action=='analyze' else read_json(self.output/('segmentation/timing_summary.json' if self.action=='segment' else 'center_search/summary.json'))
        if not summary:raise RuntimeError('Backend returned without a completion summary')
        if self.action=='segment':summary={'images':summary['images'],'folder':str(self.output/'segmentation'),'timings':summary}
        return summary
    def prepare_dataset(self):
        sys.path.insert(0,str(FINETUNE));from finetune_gui.data import DataProject
        project=DataProject.load(Path(self.s['dataset']));plan=project.plan_split('all',self.s['train_percent'],self.s['seed'])
        project.apply_split(plan);destination=self.output/'dataset'
        def progress(done,total):self.check();self.emit(phase='Saving split dataset',completed=done,total=total)
        project.export(destination,progress=progress)
        return dict(dataset=str(destination),train=plan.count('train'),validation=plan.count('val'))
    def train(self):
        sys.path.insert(0,str(FINETUNE))
        from finetune_gui.training import TrainingSettings,render_config,dataset_summary,config_name_for
        s=self.s;data=dataset_summary(Path(s['dataset']))
        if any(data[k]['images']<1 for k in ('train','val')):raise ValueError('Training and Validation must both contain images')
        if not data['train']['categories'] or data['train']['categories']!=data['val']['categories']:raise ValueError('Training/Validation category lists must match')
        experiment=self.output/'experiment';experiment.mkdir()
        base=s['checkpoint'];resume=s['resume_checkpoint'] if self.action=='resume_training' else None
        if resume:
            meta=read_json(Path(resume).parent.parent/'gui_launch.json')
            if meta:
                if meta.get('dataset')!=wsl(s['dataset']) or meta.get('gpu_ids')!=str(s['gpu']):raise ValueError('Resume requires the original dataset and GPU IDs')
                base=meta.get('initial_checkpoint',base)
        # Select the original WSL template through a Windows UNC path. Never edit it.
        template=Path('\\\\wsl.localhost\\'+s['distro']+s['training_template'].replace('/','\\'))
        settings=TrainingSettings(config=template,dataset=Path(s['dataset']),output=Path(experiment),checkpoint=Path(base),
             epochs=s['epochs'],batch_size=s['batch_size'],gpus=1,workers=s['workers'],val_every=s['val_every'],
             save_every=s['save_every'],lr_scale=s['lr_scale'],resume_from=Path(resume) if resume else None,
             repository=Path(s['training_repo']),python=Path(s['training_python']),category='finetune')
        import yaml
        rendered=render_config(settings)
        runtime=yaml.safe_load(rendered)
        model_options=runtime['trainer']['model']
        model_options.update(checkpoint_path=wsl(base),device='cpu',load_from_HF=False)
        if 'num_val_workers' in runtime.get('scratch',{}):runtime['scratch']['num_val_workers']=s['workers']
        rendered='# @package _global_\n'+yaml.safe_dump(runtime,sort_keys=False)
        name='assistant_'+self.folder.name
        # Config name is unique per owned task, even though output leaf is always experiment.
        runtime_config=s['training_repo']+'/sam3/train/configs/gui_runs/'+name+'.yaml'
        runtime_host=Path('\\\\wsl.localhost\\'+s['distro']+runtime_config.replace('/','\\'))
        runtime_host.parent.mkdir(parents=True,exist_ok=True);runtime_host.write_text(rendered,encoding='utf-8')
        atomic_json(experiment/'gui_launch.json',dict(initial_checkpoint=wsl(base),dataset=wsl(s['dataset']),gpu_ids=str(s['gpu']),runtime_config=runtime_config))
        target=resume or base
        preflight="import torch,sam3,hydra,pycocotools;torch.set_num_threads(8);print('BL62_TRAIN_STAGE checking_checkpoint',flush=True);assert torch.cuda.is_available(),'CUDA unavailable';p=torch.load("+repr(wsl(target))+",map_location='cpu',weights_only=False,mmap=True);assert isinstance(p,dict),'Invalid checkpoint';"
        if resume:preflight+=f"assert 'optimizer' in p and 'epoch' in p,'A full training checkpoint is required';assert int(p['epoch']) < {s['epochs']},'Epochs must exceed the saved epoch';"
        else:preflight+="assert 'model' in p or any(hasattr(v,'shape') for v in p.values()),'Invalid model weights';"
        stop_path=wsl(self.output/'stop_requested');ready_path=wsl(self.output/'training.signal_ready')
        bootstrap="import os,signal,sys;from pathlib import Path;signal.signal(signal.SIGINT,signal.SIG_DFL);signal.signal(signal.SIGTERM,signal.SIG_DFL);sys.exit(130) if os.path.exists("+repr(stop_path)+") else None;Path("+repr(ready_path)+").write_text(str(os.getpid()));os.execvpe(sys.argv[1],sys.argv[1:],os.environ)"
        train_args=[s['training_python'],'-u','-c',bootstrap,s['training_python'],'-u','-m','sam3.train.train','-c','configs/gui_runs/'+name+'.yaml','--use-cluster','0','--num-gpus','1']
        script='#!/bin/bash\nset -e\ncd '+shlex.quote(s['training_repo'])+'\nexport PYTHONNOUSERSITE=1\nexport OMP_NUM_THREADS=8\nexport MKL_NUM_THREADS=8\nexport OPENBLAS_NUM_THREADS=8\nexport CUDA_VISIBLE_DEVICES='+str(s['gpu'])+'\n'
        script+=shlex.join([s['training_python'],'-c',preflight])+'\n'
        script+='[ -f '+shlex.quote(wsl(self.output/'stop_requested'))+' ] && exit 130\n'
        script+='echo "BL62_TRAIN_STAGE launching_training"\n'
        script+='setsid '+shlex.join(train_args)+' &\nchild=$!\nprintf "%s" "$child" > '+shlex.quote(wsl(self.output/'training.pid'))+'\n'
        script+='if [ -f '+shlex.quote(wsl(self.output/'stop_requested'))+' ]; then kill -INT -- -"$child"; fi\nwait "$child"\n'
        launcher=self.folder/'launch_training.sh';launcher.write_text(script,encoding='utf-8',newline='\n')
        def progress():
            stats=experiment/'logs/finetune/train_stats.json';values=[]
            if stats.is_file():
                for line in stats.read_text(encoding='utf-8',errors='replace').splitlines()[-5:]:
                    try:values.append(json.loads(line))
                    except ValueError:pass
            last=values[-1] if values else {};epoch=int(last.get('Trainer/epoch',-1))+1
            log=self.folder/'backend.log'
            with log.open('rb') as f:
                if log.stat().st_size>128000:f.seek(-128000,2)
                tail=f.read().decode('utf-8',errors='replace')
            phase='Checking training environment and checkpoint';known=False
            if 'BL62_TRAIN_STAGE launching_training' in tail:phase='Starting training process'
            if 'Setting up components' in tail:phase='Loading SAM3 training model'
            if 'Train Epoch:' in tail or values:phase='Training SAM3';known=True
            if tail.rfind('Val Epoch:')>tail.rfind('Train Epoch:'):phase='Validating model'
            if 'Saving checkpoint' in tail[-3000:]:phase='Saving training checkpoint';known=False
            temp_checkpoint=experiment/'checkpoints/checkpoint.pt.tmp'
            if temp_checkpoint.is_file():phase=f'Saving training checkpoint · {temp_checkpoint.stat().st_size/2**30:.2f} GiB written';known=False
            self.emit(phase=phase,completed=max(0,epoch),total=s['epochs'] if known else 0,metrics=last)
        args=['C:/Windows/System32/wsl.exe','-d',s['distro'],'--','bash',wsl(launcher)]
        self.run_child(args,'Checking training environment',progress,training=True)
        checkpoint=experiment/'checkpoints/checkpoint.pt'
        if not checkpoint.is_file():raise RuntimeError('Training ended without the expected full checkpoint')
        converted=experiment/'checkpoints/checkpoint_sam3_format.pt'
        converter=FINETUNE/'finetune_gui/convert_checkpoint.py'
        convert_args=['env','PYTHONNOUSERSITE=1','CUDA_VISIBLE_DEVICES=',s['training_python'],'-u','-c',bootstrap,s['training_python'],'-u',wsl(converter),'--base',wsl(base),'--training',wsl(checkpoint),'--output',wsl(converted),'--fallback-base',s['training_repo']+'/sam3.pt']
        script='#!/bin/bash\nset -e\nsetsid '+shlex.join(convert_args)+' &\nchild=$!\nprintf "%s" "$child" > '+shlex.quote(wsl(self.output/'training.pid'))+'\nwait "$child"\n'
        conversion_launcher=self.folder/'launch_conversion.sh';conversion_launcher.write_text(script,encoding='utf-8',newline='\n')
        args=['C:/Windows/System32/wsl.exe','-d',s['distro'],'--','bash',wsl(conversion_launcher)]
        def converting():
            progress=None
            with (self.folder/'backend.log').open('rb') as f:
                size=(self.folder/'backend.log').stat().st_size
                if size>16000:f.seek(-16000,2)
                lines=f.read().decode('utf-8',errors='replace').splitlines()
            for line in lines:
                if line.startswith('BL62_CONVERSION '):
                    try:progress=json.loads(line[len('BL62_CONVERSION '):])
                    except ValueError:pass
            if progress:self.emit(phase='Training complete · Converting · '+progress.get('message',''),completed=progress.get('progress',0),total=100)
        self.run_child(args,'Training complete. Converting inference model',progress=converting,training=True)
        if not converted.is_file():raise RuntimeError('Inference conversion did not produce its checkpoint')
        return dict(checkpoint=str(checkpoint),inference_checkpoint=str(converted),experiment=str(experiment),dataset=data)
    def run(self):
        self.emit();validate_job(self.action,self.s);self.check()
        if self.action=='inspect_data':result=self.inspect()
        elif self.action=='reconstruct':result=self.reconstruct()
        elif self.action in ('try_center','try_angle'):result=self.trial()
        elif self.action in ('find_center','analyze','segment'):result=self.sam()
        elif self.action=='prepare_dataset':result=self.prepare_dataset()
        else:result=self.train()
        self.check();atomic_json(self.output/'result.json',result)
        self.emit(state='succeeded',phase='Task completed',completed=1,total=1,result=result)

def sam_engine(kind,path):
    cfg=read_json(path);os.environ['CUDA_VISIBLE_DEVICES']=str(cfg['gpu']);os.environ['PYTHONNOUSERSITE']='1'
    sys.path.insert(0,cfg['repo']);sys.path.insert(0,str(RECON))
    from analysis_worker import Pipeline
    pipeline=Pipeline(cfg)
    if kind=='segment':
        pipeline.load_model();files=[Path(p) for p in read_json(Path(path).parent/'image_manifest.json',[])];pipeline.segment(files)
    elif kind=='find_center':pipeline.find_center()
    else:pipeline.run()

def main():
    p=argparse.ArgumentParser();p.add_argument('--job');p.add_argument('--sam-engine');p.add_argument('--config');args=p.parse_args()
    if args.sam_engine:sam_engine(args.sam_engine,args.config);return 0
    worker=Worker(args.job)
    try:worker.run();return 0
    except Cancelled:worker.emit(state='stopped',phase='Stopped safely');return 2
    except Exception as error:
        traceback.print_exc();worker.emit(state='failed',phase='Task failed',error=str(error));return 1

if __name__=='__main__':raise SystemExit(main())
