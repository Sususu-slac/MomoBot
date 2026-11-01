"""A bounded command contract. Model output is data, never executable code."""
from dataclasses import dataclass,asdict
import json,math

ACTIONS=['inspect_data','set_parameters','reconstruct','find_center','analyze','segment',
         'try_center','try_angle','prepare_dataset','train','resume_training','status','stop','open_output','help','clarify']
FIELDS={
 'input_hdf5':'path','image_folder':'path','dataset':'path','checkpoint':'path','resume_checkpoint':'path','output_root':'path',
 'gpu':'int','center':'float','start_row':'int','end_row':'int','method':'str','geometry':'str',
 'lamino_angle':'float','binning':'int','chunk_size':'int','iterations':'int','prompt':'str',
 'confidence':'float','nms_iou':'float','max_images':'int','segment_all':'bool','range_low':'optional_float',
 'range_high':'optional_float','initial_step':'optional_float','target_step':'float','search_row':'optional_int',
 'epochs':'int','batch_size':'int','workers':'int','val_every':'int','save_every':'int','lr_scale':'float',
 'train_percent':'int','seed':'int','trial_row':'optional_int','trial_width':'float','trial_step':'float'}
SCHEMA={'type':'object','additionalProperties':False,'properties':{
 'action':{'type':'string','enum':ACTIONS},
 'updates':{'type':'array','maxItems':12,'items':{'type':'object','additionalProperties':False,
    'properties':{'field':{'type':'string','enum':list(FIELDS)},'value':{'type':'string'}},'required':['field','value']}},
 'message':{'type':'string','maxLength':400}},'required':['action','updates','message']}

SYSTEM='''You are BL62 Assistant Lab, an offline command interpreter for scientific desktop software.
Return exactly one JSON object conforming to the supplied schema. No code, shell commands or markdown.
Select ONE action. Extract ONLY values explicitly requested by the user. Omitted settings inherit the current context.
Never invent file paths, center coordinates or measurements. The current context is authoritative, not a prior plan.
Actions:
inspect_data: read metadata for the selected input. set_parameters: change settings without starting a job.
reconstruct: reconstruct using the entered center; find_center: find a center only (SAM3 adaptive search).
analyze: predefined center search followed by reconstruction and optional Segment All. When BOTH finding center AND reconstruction are requested, choose analyze, not find_center.
segment: segment images from image_folder with SAM3. max_images=0 means ALL, otherwise the number of images.
prepare_dataset: export a train/validation split from a COCO dataset folder/JSON, using train_percent and seed.
train: NEW SAM3 fine-tuning. resume_training: continue from resume_checkpoint and a greater TOTAL epochs target.
status: current job status/log information. stop: stop the active job. open_output: open that job's output folder.
help: explain available commands. clarify: ask a short question if the request is ambiguous or unsupported.
Rules: changing parameters alone is set_parameters, NOT a compute job. Safe Stop means stop.
"train" means model training; "segment" means SAM3 prediction, never training. Never switch a GPU unless asked.
For resume_training, do not copy checkpoint into resume_checkpoint. Leave resume_checkpoint unchanged unless the user explicitly provides its path.
"all images" explicitly sets max_images=0. "no segmentation" sets segment_all=false.
"2x2 binning" sets binning=1; "4x4" sets binning=2; "8x8" sets binning=3; original resolution sets binning=0.
Percent confidence becomes a fraction, e.g. 35% -> 0.35. Row ranges are [start_row,end_row), end exclusive.
Use method IDs: fourierrec,lprec,linerec,fbp_cuda,sirt_cuda,cgls_cuda. geometry: tomography or laminography.
Do not start a sequence of separate jobs. For unsupported automatic workflows, ask the user to choose one task.
You cannot judge images, edit code, delete source data, overwrite existing labels or manage arbitrary programs.
Automatic center search / analyze supports TOMOGRAPHY ONLY. There is no automatic laminography angle-search action: clarify instead.
Training in this test application uses ONE Task GPU. If multiple GPUs are requested for one training job, clarify instead of choosing one silently.
Do not claim a job has run. The user reviews and executes the returned plan in the application.
Examples:
User: Set GPU to 0. -> {"action":"set_parameters","updates":[{"field":"gpu","value":"0"}],"message":"Set GPU to 0."}
User: Reconstruct rows 1000 to 1005 using FBP on GPU 1. -> {"action":"reconstruct","updates":[{"field":"start_row","value":"1000"},{"field":"end_row","value":"1005"},{"field":"method","value":"fbp_cuda"},{"field":"gpu","value":"1"}],"message":"Reconstruct the requested rows."}
User: Segment all images with prompt particle. -> {"action":"segment","updates":[{"field":"max_images","value":"0"},{"field":"prompt","value":"particle"}],"message":"Segment all images."}
User: Train for 2 epochs. -> {"action":"train","updates":[{"field":"epochs","value":"2"}],"message":"Start a new 2-epoch training job."}
User: Find center then reconstruct without segmentation. -> {"action":"analyze","updates":[{"field":"segment_all","value":"false"}],"message":"Plan center search and reconstruction."}
User: Resume for a total of 10 epochs. -> {"action":"resume_training","updates":[{"field":"epochs","value":"10"}],"message":"Resume using the selected full checkpoint."}
User: What is happening? -> {"action":"status","updates":[],"message":"Show the current task status."}
'''

@dataclass
class Plan:
    action:str
    updates:dict
    message:str
    def to_dict(self):return asdict(self)

def parse_plan(raw):
    value=json.loads(raw) if isinstance(raw,str) else raw
    if not isinstance(value,dict) or set(value)!=set(SCHEMA['required']):raise ValueError('Invalid plan structure')
    if value['action'] not in ACTIONS:raise ValueError('Unknown action')
    if not isinstance(value['message'],str) or len(value['message'])>400:raise ValueError('Invalid plan message')
    if not isinstance(value['updates'],list) or len(value['updates'])>12:raise ValueError('Invalid parameter list')
    updates={}
    for pair in value['updates']:
        if not isinstance(pair,dict) or set(pair)!={'field','value'}:raise ValueError('Invalid parameter item')
        name,text=pair['field'],pair['value']
        if name not in FIELDS or name in updates:raise ValueError('Unknown or duplicate parameter: '+str(name))
        if not isinstance(text,str) or len(text)>2048:raise ValueError('Invalid parameter value')
        kind=FIELDS[name]
        if kind.startswith('optional_') and text.lower() in ('null','none','auto','global'):parsed=None
        elif kind.endswith('int'):
            if not text.strip().lstrip('-').isdigit():
                if name=='gpu':raise ValueError('Select one Task GPU in this test GUI; multi-GPU training is not supported here')
                raise ValueError(name+' must be an integer')
            parsed=int(text)
        elif kind.endswith('float'):
            parsed=float(text)
            if not math.isfinite(parsed):raise ValueError(name+' must be finite')
        elif kind=='bool':
            if text.lower() not in ('true','false'):raise ValueError(name+' must be true or false')
            parsed=text.lower()=='true'
        else:
            if any(ord(c)<32 for c in text):raise ValueError('Control characters are not allowed')
            parsed=text.strip()
            if name=='method':
                aliases={m.replace('_',''):m for m in ('fourierrec','lprec','linerec','fbp_cuda','sirt_cuda','cgls_cuda')}
                spelling=parsed.lower().replace('_','').replace(' ','').replace('-','')
                parsed=aliases.get(spelling,parsed)
        updates[name]=parsed
    if value['action'] in ('status','stop','open_output','help','clarify') and updates:raise ValueError('This action cannot change parameters')
    return Plan(value['action'],updates,value['message'])

def validate_settings(s):
    if s.get('trial_width',1)<=0 or s.get('trial_step',1)<=0:raise ValueError('Trial width and step must be positive')
    for name in ('gpu','start_row','binning','workers','save_every','seed','max_images'):
        if not isinstance(s[name],int) or isinstance(s[name],bool) or s[name]<0:raise ValueError(name+' must be a nonnegative integer')
    for name in ('end_row','chunk_size','iterations','epochs','batch_size','val_every'):
        if not isinstance(s[name],int) or isinstance(s[name],bool) or s[name]<1:raise ValueError(name+' must be a positive integer')
    for name in ('center','lamino_angle','confidence','nms_iou','target_step','lr_scale'):
        if isinstance(s[name],bool) or not isinstance(s[name],(int,float)) or not math.isfinite(s[name]):raise ValueError(name+' must be a finite number')
    if s['end_row']<=s['start_row']:raise ValueError('End row must be greater than Start row (exclusive)')
    if s['binning'] not in (0,1,2,3):raise ValueError('Unsupported binning')
    if s['geometry'] not in ('tomography','laminography'):raise ValueError('Unsupported geometry')
    if s['method'] not in ('fourierrec','lprec','linerec','fbp_cuda','sirt_cuda','cgls_cuda'):raise ValueError('Unsupported reconstruction method')
    if not 0<s['confidence']<1 or not 0<=s['nms_iou']<=1:raise ValueError('Confidence / NMS out of range')
    if s['target_step'] not in (.25,.5,1.):raise ValueError('Target step must be 0.25, 0.5 or 1')
    if not 1<=s['train_percent']<=99:raise ValueError('Train percentage must be 1–99')
    if s['lr_scale']<=0:raise ValueError('LR scale must be positive')
    for name in ('range_low','range_high','initial_step','search_row'):
        v=s[name]
        if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0):raise ValueError('Invalid '+name)
    if (s['range_low'] is None)!=(s['range_high'] is None):raise ValueError('Set both search-range limits, or leave both automatic')
    if s['range_low'] is not None and s['range_high']<=s['range_low']:raise ValueError('Search range must increase')
    return s

def apply_plan(settings,plan):
    result={**settings,**plan.updates}
    if 'input_hdf5' in plan.updates and plan.updates['input_hdf5']!=settings['input_hdf5'] and 'center' not in plan.updates:
        result['center']=0.0
    validate_settings(result);return result
