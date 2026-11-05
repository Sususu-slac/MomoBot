"""Persistent task conversations and an explicit, reviewable workflow."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json,uuid,copy
from .config import STATE_ROOT,ROOT,DEFAULTS
from .jobs import atomic_json,read_json
from .protocol import apply_plan

TITLES={'reconstruct':'Reconstruct data','segment':'Segment images','train':'Fine-tune model',
        'prepare_dataset':'Prepare dataset','find_center':'Find rotation center','analyze':'Smart reconstruction',
        'try_center':'Try rotation centers','try_angle':'Try lamino angles'}
PATHS={'input_hdf5','image_folder','dataset','checkpoint','resume_checkpoint','output_root'}

def message(task,role,text,sticker=None):
    entry=dict(id=uuid.uuid4().hex,role=role,text=str(text),time=datetime.now().isoformat())
    if sticker:entry['sticker']=sticker
    task['messages'].append(entry)

def new_task():
    return dict(id=datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid.uuid4().hex[:8],title='New task',
        created=datetime.now().isoformat(),kind=None,settings=copy.deepcopy(DEFAULTS),done=[],messages=[],
        jobs=[],state='draft',center_mode=None,metadata={},draft='',prepared=False,needs_split=False)

class Conversations:
    def __init__(self,root=None):self.root=Path(root or STATE_ROOT/'conversations');self.root.mkdir(parents=True,exist_ok=True)
    def save(self,task):
        if task.get('_deleted'):return
        atomic_json(self.root/(task['id']+'.json'),task)
    def allows_empty(self):return (self.root/'.empty_allowed').exists()
    def delete(self,identity):
        if not identity or identity in ('.','..') or '/' in identity or '\\' in identity:
            raise ValueError('Invalid task ID')
        # Remember an intentionally empty task list, without retaining deleted chats.
        (self.root/'.empty_allowed').touch()
        (self.root/(identity+'.tmp')).unlink(missing_ok=True)
        (self.root/(identity+'.json')).unlink(missing_ok=True)
    def all(self):
        return [v for p in sorted(self.root.glob('*.json'),reverse=True) if (v:=read_json(p)) and v.get('id')==p.stem]
    def create(self):
        task=new_task();message(task,'assistant',"Hi, I'm MomoBot. Tell me what you would like to do and paste the data path. I can reconstruct data, generate trial reconstructions, find a center, segment images or fine-tune a model.");self.save(task);return task

def mark(task,*names):task['done']=list(dict.fromkeys(task['done']+list(names)))

def choose_kind(task,kind):
    if kind not in TITLES:raise ValueError('Choose a supported task')
    task['kind']=kind;task['title']=TITLES[kind];task['state']='draft'
    if kind=='analyze':task['center_mode']='auto'

def step(task):
    if task['state'] in ('running','stopping'):return 'running'
    if task['state']=='completed':return 'completed'
    kind=task['kind'];s=task['settings'];done=task['done']
    if not kind:return 'kind'
    source='image_folder' if kind=='segment' else 'dataset' if kind in ('train','prepare_dataset') else 'input_hdf5'
    if source not in done:return source
    if kind in ('reconstruct','analyze'):
        if not task.get('center_mode'):return 'center_mode'
        if task['center_mode']=='known' and s['center']<=0:return 'center'
        if 'rows' not in done:return 'rows'
    if kind in ('segment','find_center','analyze') or task.get('center_mode')=='auto':
        if 'prompt' not in done:return 'prompt'
    if kind=='segment' and 'limit' not in done:return 'limit'
    if kind in ('train','prepare_dataset'):
        if (kind=='prepare_dataset' or task.get('needs_split')) and not task.get('prepared'):
            if 'split' not in done:return 'split'
            return 'ready'
        if kind=='train' and 'epochs' not in done:return 'epochs'
    return 'ready'

def action(task):
    kind=task['kind']
    if kind=='train' and task.get('needs_split') and not task.get('prepared'):return 'prepare_dataset'
    if kind=='reconstruct' and task.get('center_mode')=='auto':return 'analyze'
    return kind

def question(task):
    current=step(task)
    if current=='kind':return '',[(v,'kind:'+k) for k,v in TITLES.items() if k!='analyze']
    if current=='input_hdf5':return 'First, choose the HDF5 data you want to work on.', [('Choose HDF5 file','browse:input_hdf5')]
    if current=='image_folder':return 'First, choose the folder containing your images.',[('Choose image folder','browse:image_folder')]
    if current=='dataset':return 'Choose a saved training dataset, or a COCO JSON file to prepare one.',[('Choose dataset folder','browse:dataset'),('Open JSON file','json:dataset')]
    if current=='center_mode':return 'Do you already know the rotation center, or should I find it?', [('Find automatically','center:auto'),('Enter known center','center:known')]
    if current=='center':return 'What is the rotation center in pixels? You can enter a value such as 1028.75.',[]
    if current=='rows':
        n=task['metadata'].get('rows')
        return (f'The data contains {n} detector rows. ' if n else '')+'Reconstruct all slices, or try five middle slices first? You can also enter a row range.',[('Five middle slices','rows:middle'),('All slices','rows:all')]
    if current=='prompt':return 'What should SAM3 look for? Enter a short English name, such as particle.',[('particle','prompt:particle')]
    if current=='limit':return f"I found {task['metadata'].get('images','the available')} images. Process them all, or try two first?",[('Try 2 images','limit:2'),('All images','limit:all')]
    if current=='split':return 'How should the dataset be split? The default is 80% training and 20% validation, with seed 42.',[('Use 80 / 20','split:80'),('Use 90 / 10','split:90')]
    if current=='epochs':return 'How many training epochs would you like? One epoch is useful for a short test.',[('Test with 1 epoch','epochs:1'),('10 epochs','epochs:10')]
    if current=='ready':return review(task), [('Start '+{'prepare_dataset':'dataset preparation','train':'training','segment':'segmentation','find_center':'center search'}.get(action(task),'reconstruction'),'run'),('Choose output folder','browse:output_root')]
    if current=='running':return 'The task is running. You can ask questions, check progress, or stop it safely.',[('Show progress','status'),('Safe Stop','stop')]
    return 'This task is complete. You can open the results, adjust parameters, or create another task.',[('Open results','open_output'),('Adjust / run again','revise'),('New task','new')]

def review(task):
    s=task['settings'];a=action(task);lines=['Ready to '+TITLES.get(a,a).lower()+'.']
    if a in ('reconstruct','analyze','find_center'):
        lines.append('Data: '+s['input_hdf5'])
        if a!='find_center':lines.append(f"Rows: {s['start_row']} to {s['end_row']} (end excluded) · {s['method']}")
        lines.append('Center: automatic search' if a in ('analyze','find_center') else f"Center: {s['center']:g} px")
        if a in ('analyze','find_center'):
            lines.append(('Search range: automatic global range' if s['range_low'] is None else f"Search range: {s['range_low']:g} to {s['range_high']:g}")+f" · Final step: {s['target_step']:g} px")
        if a=='analyze':lines.append('Segment reconstructed slices: '+('yes' if s['segment_all'] else 'no'))
    elif a=='segment':lines.extend(['Images: '+s['image_folder'],f"Prompt: {s['prompt']} · Images: {s['max_images'] or 'all'} · Confidence: {s['confidence']:g}"])
    elif a=='prepare_dataset':lines.extend(['Data: '+s['dataset'],f"Split: {s['train_percent']}% training / {100-s['train_percent']}% validation · Seed {s['seed']}"])
    elif a=='train':lines.extend(['Dataset: '+s['dataset'],f"Epochs: {s['epochs']} · Batch: {s['batch_size']} · Workers: {s['workers']}"])
    elif a in ('try_center','try_angle'):
        lines.extend(['Data: '+s['input_hdf5'],f"One detector row: {s.get('trial_row') if s.get('trial_row') is not None else 'middle'}",f"Candidate half-width: {s.get('trial_width',10):g} · Step: {s.get('trial_step',1):g}",'Selection: you compare the candidates and choose the best value'])
    if a not in ('prepare_dataset',):lines.append(f"GPU: {s['gpu']}")
    if a in ('segment','find_center','analyze','train'):lines.append('Checkpoint: '+s['checkpoint'])
    lines.extend(['Output: a new folder under '+s['output_root'],'You can change any setting in chat before starting.'])
    return '\n'.join(lines)

def validate_geometry(task,s):
    meta=task['metadata']
    if meta.get('rows') and not 0<=s['start_row']<s['end_row']<=meta['rows']:raise ValueError(f"Choose rows within 0 to {meta['rows']} (end excluded).")
    if meta.get('width') and s['center'] and not 0<s['center']<meta['width']:raise ValueError('The center must be inside the detector width.')

def apply_response(task,plan,center_mode='unchanged',row_scope='unchanged',accept_defaults=False):
    draft=copy.deepcopy(task)
    _apply_response(draft,plan,center_mode,row_scope,accept_defaults)
    task.clear();task.update(draft)

def _apply_response(task,plan,center_mode='unchanged',row_scope='unchanged',accept_defaults=False):
    """Only update the captured conversation. This function cannot submit a job."""
    if task['state'] in ('running','stopping','completed'):
        if plan.updates:raise ValueError('This task is not being edited. Choose Adjust / run again, or create a new task.')
        return
    if task['kind'] is None and plan.action in TITLES:choose_kind(task,plan.action)
    if task['kind'] is None:
        for field,kind in [('input_hdf5','reconstruct'),('image_folder','segment'),('dataset','train')]:
            if field in plan.updates:choose_kind(task,kind);break
    expected='image_folder' if task['kind']=='segment' else 'dataset' if task['kind'] in ('train','prepare_dataset') else 'input_hdf5'
    if any(name in plan.updates for name in {'input_hdf5','image_folder','dataset'}-{expected}):raise ValueError('Create a new task to work with a different input type.')
    before=step(task);s=apply_plan(task['settings'],plan)
    for name in PATHS:
        if name in plan.updates and plan.updates[name]!=task['settings'][name]:
            # A selected path is inspected before it becomes a usable input.
            task['done']=[x for x in task['done'] if x!=name]
    if 'input_hdf5' in plan.updates and plan.updates['input_hdf5']!=task['settings']['input_hdf5']:
        task['metadata']={};task['center_mode']=None;task['done']=[x for x in task['done'] if x not in ('rows','center')]
    if 'dataset' in plan.updates and plan.updates['dataset']!=task['settings']['dataset']:
        task['prepared']=False;task['needs_split']=False
    mode=task.get('center_mode')
    if 'center' in plan.updates and s['center']>0:mode='known'
    if center_mode!='unchanged':mode=center_mode
    if row_scope!='unchanged':
        n=task['metadata'].get('rows')
        if not n:raise ValueError('Choose and inspect the HDF5 file first.')
        s['start_row'],s['end_row']=(0,n) if row_scope=='all' else (max(0,n//2-2),min(n,n//2+3))
    validate_geometry(task,s);task['settings']=s;task['center_mode']=mode
    if any(k in plan.updates for k in ('start_row','end_row')) or row_scope!='unchanged':mark(task,'rows')
    if 'prompt' in plan.updates:mark(task,'prompt');task['prompt_confirmed']=True
    if 'max_images' in plan.updates:mark(task,'limit')
    if 'train_percent' in plan.updates:mark(task,'split')
    if 'epochs' in plan.updates:mark(task,'epochs')
    if accept_defaults and before in ('prompt','limit','split','epochs'):
        if before=='limit':task['settings']['max_images']=2
        mark(task,before)

def set_source(task,field,value):
    if not value:return
    if field=='output_root':task['settings'][field]=value;return
    if field not in PATHS:raise ValueError('Unsupported input')
    if task['state'] in ('running','stopping'):raise ValueError('Wait for this task before changing its input')
    changed=task['settings'][field]!=value;task['settings'][field]=value
    task['done']=[x for x in task['done'] if x!=field]
    if changed and field=='input_hdf5':
        task['settings']['center']=0.;task['center_mode']=None;task['metadata']={};task['done']=[x for x in task['done'] if x!='rows']
    if changed and field=='dataset':task['prepared']=False;task['needs_split']=False

def inspect_source(field,value):
    """Metadata only; original image/annotation content is never changed."""
    p=Path(value)
    if field=='input_hdf5':
        import sys
        from .config import RECON
        sys.path.insert(0,str(RECON));from ct_recon_gui.hdf5_inspector import inspect_hdf5
        info=inspect_hdf5(p);return dict(rows=info.data_shape[1],width=info.data_shape[2],projections=info.data_shape[0],dtype=info.data_dtype,size_bytes=p.stat().st_size,theta_min=info.theta_min,theta_max=info.theta_max,theta_unit=info.theta_unit,white_shape=list(info.white_shape),dark_shape=list(info.dark_shape))
    if field=='image_folder':
        if not p.is_dir():raise ValueError('Choose an existing image folder')
        n=sum(f.is_file() and f.suffix.lower() in ('.png','.tif','.tiff','.jpg','.jpeg','.bmp') for f in p.iterdir())
        if not n:raise ValueError('No supported images in this folder')
        return dict(images=n)
    if field=='dataset':
        if p.is_dir() and (p/'train/annotations.json').is_file() and (p/'val/annotations.json').is_file():
            from .config import FINETUNE
            import sys
            sys.path.insert(0,str(FINETUNE));from finetune_gui.training import dataset_summary
            data=dataset_summary(p)
            if any(data[k]['images']<1 for k in ('train','val')):raise ValueError('Training and validation both need images')
            return dict(needs_split=False,train_images=data['train']['images'],validation_images=data['val']['images'])
        from .config import FINETUNE
        import sys
        sys.path.insert(0,str(FINETUNE));from finetune_gui.data import DataProject
        project=DataProject.load(p)
        if len(project.images)<2:raise ValueError('At least two images are needed for a training/validation split')
        if not any(rec['annotations'] for rec in project.images):raise ValueError('Choose a COCO JSON or a dataset containing annotations')
        return dict(needs_split=True,images=len(project.images))
    if not p.is_file():raise ValueError('Choose an existing file')
    return {}

def accept_source(task,field,value,metadata):
    if task['settings'].get(field)!=value:return False
    if field=='input_hdf5':
        values=dict(task['settings'])
        if 'rows' not in task['done']:
            n=metadata['rows'];values.update(start_row=max(0,n//2-2),end_row=min(n,n//2+3))
        check={**task,'metadata':metadata};validate_geometry(check,values)
        task['settings']=values
    mark(task,field)
    if field=='dataset':task['needs_split']=metadata['needs_split']
    if field in ('input_hdf5','image_folder','dataset'):task['metadata']=metadata
    if field=='input_hdf5':
        task['title']=TITLES[task['kind']]+' · '+Path(value).stem
    elif field in ('image_folder','dataset'):task['title']=TITLES[task['kind']]+' · '+Path(value).name
    return True
