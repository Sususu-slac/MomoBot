"""Typed model interpretation, validated before the reconstruction state machine acts."""
from __future__ import annotations
import copy,json,math,re
from pathlib import Path
from .protocol import FIELDS,parse_plan
from .path_rules import path_key

EXTRA_FIELDS={'remove_stripe_method':'str','dezinger':'int','dezinger_threshold':'int','filter_name':'str','bright_ratio':'float','minus_log':'bool','flat_linear':'bool'}
RECO_FIELDS={k:v for k,v in FIELDS.items() if k not in ('epochs','batch_size','workers','val_every','save_every','lr_scale','train_percent','seed','resume_checkpoint')}
RECO_FIELDS.update(EXTRA_FIELDS)
INTENTS=['configure','request','confirm','execute','select','instance','cancel','status','result','explain','clarify']
OPERATIONS=['unchanged','reconstruct','find_center','analyze','try_center','try_angle','segment','train','inspect','measure_time']
QUERIES=['none','center','time','slice','score','output','open_curve','open_best_image','open_folder']
TURN_SCHEMA={'type':'object','additionalProperties':False,'properties':{
 'intent':{'type':'string','enum':INTENTS},'operation':{'type':'string','enum':OPERATIONS},
 'mode':{'type':'string','enum':['unchanged','manual','auto']},'row_scope':{'type':'string','enum':['unchanged','all','middle']},
 'updates':{'type':'array','maxItems':24,'items':{'type':'object','additionalProperties':False,'properties':{'field':{'type':'string','enum':list(RECO_FIELDS)},'value':{'type':'string'}},'required':['field','value']}},
 'selection':{'type':'string'},'query':{'type':'string','enum':QUERIES},'message':{'type':'string'}},
 'required':['intent','operation','mode','row_scope','updates','selection','query','message']}

SYSTEM='''You are MomoBot's reconstruction interpreter. Understand EVERY new reconstruction message before any application rules handle it. Reason carefully about context, user intent, numbers, units, negations, corrections and the current workflow phase. Return ONLY the schema's JSON. message is a short public understanding or clarification, NOT private reasoning.
Never claim execution or completion. Never invent paths, measurements, a known center, GPU, feature or acquisition geometry. Existing settings are context, not new updates. Extract only explicitly requested settings. Include explicitly stated values even when they equal the current value, especially when selecting a new input. Omit inherited settings that were not mentioned. If you cannot understand a material parameter, return clarify with a specific question; never silently reuse a default while claiming it was updated.
Phases: path/file/reading/geometry/angle/mode/target/instance/trial_offer/search_offer/choose/choose_angle/confirm/center_ready/complete/paused/interrupted/edit_error/parameters.
intent configure changes settings without execution. request starts PLANNING an operation; computation still waits for the application's confirmation. execute is an explicit command to generate trials or start center search. confirm means accepting the current reviewed plan or offer, with no new parameters. select means a candidate/file choice. instance asks to paint/provide an example. cancel pauses/stops this task. result asks for a SAVED fact/artifact. explain is a conceptual/contextual question and changes nothing. clarify asks for missing/ambiguous information.
operation measure_time explicitly requests a few-slice timing pilot (not a full reconstruction); a question about expected time is intent result, query time. operation reconstruct uses a KNOWN center. analyze explicitly requests automatic center finding followed by full reconstruction. find_center ONLY searches, never full-reconstructs. try_center/try_angle generate trial images for the user to select. Automatic tilt-angle scoring is unsupported. mode manual means user selection/known center; auto means SAM3 center scoring. If no preference was supplied, leave mode unchanged so the app asks. Geometry is tomography or laminography; BOTH can contain theta. Never infer geometry from a file/directory name or theta. An explicit signed lamino angle implies laminography. Missing tilt/feature/center must be asked, never filled from defaults.
Use exact user-supplied paths in path updates. A bare HDF5 path supplies input_hdf5. Do not invent child paths when selecting from a file list; use selection='file 2'. Same-input references inherit their current path without copying it into updates. File/image ordinals are one-based. selection may be 'candidate 3', 'center 807.5', 'angle -20', or an actual filename. Never choose an image from 'the sharpest one' without a user-supplied number/value/filename.
A ± B means CENTER A, HALF-WIDTH B: lower=A-B, upper=A+B. 'please 807.5 ± 50 px, step 1' during trial_offer means configure center=807.5, trial_width=50, trial_step=1. It is NOT permission to generate candidates. '+/-', 'plus or minus', '正负', radius, half-width mean the same. '757.5 to 857.5' is bounds; in manual trials use center=807.5, trial_width=50. In auto search use range_low/range_high and initial_step. Angle trials use lamino_angle as anchor and trial_width/trial_step in DEGREES. E.g. '-20 ± 2 degrees, step .25' means lamino_angle=-20, trial_width=2, trial_step=0.25, not rotation center=-20.
Search-center distances use detector pixels. If the user gives mm/µm without a recorded pixel size, ask for clarification; do not guess a conversion. Numbers must retain precision. Update values are STRINGS; booleans use 'true'/'false'; optional auto/middle fields use 'none'. Binning is an exponent: 1x1=0,2x2=1,4x4=2,8x8=3. Middle detector row means trial_row/search_row='none', not zero. Row ranges are start_row/end_row with end excluded; search bounds are NOT row limits. A step alone changes only the applicable step. 'twice as wide' derives a half-width from the current half-width. Explicit settings overrule a prior proposal. Do not parse a negated number as the requested one.
During confirm, 'yes but GPU 1' is configure, NOT confirm; changed settings need a fresh review. A bare yes in center_ready or complete is NOT permission to start a new computation. Ask what should happen next. 'Only find center', 'do not reconstruct' means find_center, even if reconstruction was mentioned negatively. 'Generate candidates with ±50' is execute with new trial settings; the app validates those changes before dispatch. While a compute job runs, do not change it; status/cancel/result/questions remain possible.
Never output arbitrary commands or deletion/software-installation actions. Unsupported requests need clarification. Scientific workers, not your prose, establish success. Every result answer must use actual_results; center=0 is unset and not a result. If no saved fact exists, say so. query chooses the fact/artifact; do not invent its value.
Examples (omit unspecified updates):
trial_offer + 'please 807.5 ± 50 px, step 1' => configure, unchanged operation/mode, updates center 807.5,trial_width 50,trial_step 1.
trial_offer + 'make it twice as wide' => configure,trial_width twice the current trial_width.
geometry + 'lamino' => configure,geometry laminography.
angle + '-20' => configure,lamino_angle -20.
target + 'particle' => configure,prompt particle.
choose + 'second image' => select,selection candidate 2.
confirm + 'yes please' => confirm,updates empty.
'what is a rotation center?' => explain,updates empty.
'''

def parse_turn(value,text,task):
    if isinstance(value,str):value=json.loads(value)
    if not isinstance(value,dict) or set(value)!=set(TURN_SCHEMA['required']):raise ValueError('Invalid reconstruction interpretation')
    for key,allowed in [('intent',INTENTS),('operation',OPERATIONS),('mode',['unchanged','manual','auto']),('row_scope',['unchanged','all','middle']),('query',QUERIES)]:
        if value[key] not in allowed:raise ValueError('Unknown interpretation '+key)
    if not isinstance(value['message'],str) or not isinstance(value['selection'],str):raise ValueError('Invalid interpretation text')
    if not isinstance(value['updates'],list) or len(value['updates'])>24:raise ValueError('Invalid reconstruction parameter list')
    updates={}
    for pair in value['updates']:
        if not isinstance(pair,dict) or set(pair)!={'field','value'}:raise ValueError('Invalid parameter item')
        key,raw=pair['field'],pair['value']
        if key not in RECO_FIELDS or key in updates or not isinstance(raw,str):raise ValueError('Unknown/duplicate reconstruction field')
        if key in FIELDS:updates[key]=parse_plan({'action':'set_parameters','updates':[pair],'message':''}).updates[key]
        else:
            kind=EXTRA_FIELDS[key]
            if kind=='int':
                if not re.fullmatch(r'-?\d+',raw):raise ValueError('Expected integer '+key)
                updates[key]=int(raw)
            elif kind=='float':updates[key]=float(raw)
            elif kind=='bool':
                if raw.lower() not in ('true','false'):raise ValueError('Expected boolean '+key)
                updates[key]=raw.lower()=='true'
            else:updates[key]=raw
        if isinstance(updates[key],float) and not math.isfinite(updates[key]):raise ValueError('Non-finite '+key)
    from .reconstruction_sop import input_paths,clean_text
    paths={path_key(p):p for p in input_paths(text)}
    for key in ('input_hdf5','output_root','checkpoint','image_folder','dataset'):
        if key not in updates:continue
        if path_key(updates[key]) in paths:updates[key]=paths[path_key(updates[key])]
        elif path_key(updates[key])==path_key(task['settings'].get(key,'')):updates.pop(key)
        else:raise ValueError('The model proposed a path you did not provide: '+key)
    if value['intent'] in ('clarify','explain','cancel','status','result','confirm','select') and updates:raise ValueError('This intent cannot edit parameters')
    if value['intent']=='confirm' and (value['mode']!='unchanged' or value['row_scope']!='unchanged'):raise ValueError('A changed plan needs review before confirmation')
    clean=clean_text(text)
    m=re.search(r'(-?\d+(?:\.\d+)?)\s*(?:±|\+\s*/\s*[-−]|plus\s+or\s+minus|正负)\s*(\d+(?:\.\d+)?)',clean,re.I)
    if m and value['intent'] not in ('clarify','explain'):
        anchor,width=map(float,m.groups());angle=task.get('sop',{}).get('trial_kind')=='angle' or value['operation']=='try_angle'
        if 'range_low' in updates and 'range_high' in updates:
            got_anchor=(updates['range_low']+updates['range_high'])/2;got_width=(updates['range_high']-updates['range_low'])/2
        else:got_anchor=updates.get('lamino_angle' if angle else 'center',task['settings'].get('lamino_angle' if angle else 'center'));got_width=updates.get('trial_width')
        if got_width is None or not math.isclose(got_width,width) or not math.isclose(got_anchor,anchor):raise ValueError('Interpretation missed the requested ± range; re-read center and half-width')
    if value['intent'] not in ('clarify','explain','result'):
        step=re.search(r'(?:\bstep|步长)\s*[:：=]?\s*(\d+(?:\.\d+)?|\.\d+)',clean,re.I)
        if step and not re.search(r"(?:not|no|don.t|do not|不要|不用)\s*(?:use\s+)?$",clean[max(0,step.start()-20):step.start()],re.I):
            auto=(value['mode']=='auto' or value['mode']=='unchanged' and task.get('sop',{}).get('mode')=='auto')
            old=task['settings'].get('initial_step' if auto else 'trial_step')
            got=updates.get('initial_step' if auto else 'trial_step',updates.get('trial_step' if auto else 'initial_step',old))
            if got is None or not math.isclose(float(got),float(step[1])):raise ValueError('Interpretation missed the explicitly requested step')
        if any(k in updates for k in ('trial_width','trial_step','range_low','range_high')) and re.search(r'\bmm\b|µm|μm|毫米|微米',clean,re.I):raise ValueError('No pixel size is recorded; clarify physical distance units before editing a pixel search range')
    if 'geometry' in updates and paths and not task.get('sop',{}).get('geometry_confirmed'):
        if re.fullmatch(r'\s*(?:please\s+)?(?:recon(?:struct)?(?:\s+it)?|重建(?:一下|它)?)?\s*[.!。！]?\s*',clean,re.I):raise ValueError('Geometry cannot be inferred from the input filename; omit geometry and let the app ask')
    if value['intent']=='configure' and not updates and value['mode']=='unchanged' and value['row_scope']=='unchanged' and value['operation']=='unchanged':raise ValueError('No requested parameter change was understood; ask for clarification instead of repeating defaults')
    result=copy.deepcopy(value);result['updates']=updates;return result

def model_context(task,text):
    from .reconstruction_sop import input_paths
    from .results import result_context
    p=task.get('sop',{});keys=('phase','mode','trial_kind','geometry_confirmed','angle_confirmed','center_valid','target_confirmed','center_only','full_requested')
    settings={k:v for k,v in task['settings'].items() if k in RECO_FIELDS}
    items=p.get('candidates',[])
    return dict(language=task.get('language','en'),task_kind=task.get('kind'),task_state=task['state'],workflow={k:p.get(k) for k in keys},settings=settings,metadata=task.get('metadata',{}),
        candidates=[{'index':x['index'],'value':x['value'],'file':Path(x['file']).name} for x in items[:16]],candidate_count=len(items),
        files=p.get('files',[])[:40],recent_conversation=[{'role':x['role'],'text':x['text'][:450]} for x in task['messages'][-4:] if x['text']],
        actual_results=result_context(task)[-2:],explicit_paths=input_paths(text),latest_user_message=text)
