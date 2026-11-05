"""Execute a validated interpretation through the existing reconstruction SOP."""
from __future__ import annotations
import copy,math,re
from pathlib import Path
from .protocol import validate_settings
from .conversations import mark
from .chat_flow import say
from .jobs import read_json


def validate_current(task):
    s=task['settings'];p=task['sop'];meta=task.get('metadata',{})
    validate_settings(s)
    if s.get('bright_ratio',1)<=0 or s.get('dezinger',0)<0 or s.get('dezinger_threshold',5000)<0:raise ValueError('Invalid preprocessing values')
    if s.get('remove_stripe_method','vo-all') not in ('none','vo-all','fw','ti'):raise ValueError('Unknown stripe removal method')
    if 'filter_name' in s and s['filter_name'] not in ('none','ramp','shepp','hann','hamming','parzen','cosine','cosine2'):raise ValueError('Unknown reconstruction filter')
    if 'lamino_angle' in s and (not math.isfinite(s['lamino_angle']) or not -89.9<=s['lamino_angle']<=89.9):raise ValueError('Lamino angle outside supported range')
    trial=p.get('trial_kind')=='angle' or p.get('force_trials') or p.get('phase') in ('trial_offer','choose','choose_angle')
    if trial:
        if 2*s['trial_width']/s['trial_step']>500:raise ValueError('More than 500 candidates; narrow the range or increase the step')
        if 2*s['trial_width']/s['trial_step']<2:raise ValueError('The range/step must produce at least two candidates')
        if p.get('trial_kind')=='angle':
            if s['lamino_angle']-s['trial_width']<=-89.9 or s['lamino_angle']+s['trial_width']>=89.9:raise ValueError('Angle search range is outside supported bounds')
        elif meta and s['center']:
            if s['center']-s['trial_width']<=0 or s['center']+s['trial_width']>=meta['width']:raise ValueError('Center search range is outside the detector width')
    if meta:
        if not 0<=s['start_row']<s['end_row']<=meta['rows']:raise ValueError('Row range is outside the selected data')
        if s['center'] and not 0<s['center']<meta['width']:raise ValueError('Rotation center is outside the detector width')
        if s['range_high'] is not None and s['range_high']>=meta['width']:raise ValueError('Automatic center range is outside the detector width')


def apply_fields(sop,task,turn):
    draft=copy.deepcopy(task);s=draft['settings'];p=draft['sop'];u=turn['updates'];op=turn['operation'];old_geometry=s['geometry']
    phase=p['phase'];s.update({k:v for k,v in u.items() if k!='input_hdf5'})
    if turn['mode']!='unchanged':p['mode']=turn['mode']
    if op=='try_angle':
        p.update(trial_kind='angle',mode='manual',force_trials=True,geometry_confirmed=True);s['geometry']='laminography'
        if 'trial_width' not in u and task.get('sop',{}).get('trial_kind')!='angle':s['trial_width']=2.
        if 'trial_step' not in u and task.get('sop',{}).get('trial_kind')!='angle':s['trial_step']=.25
    elif op=='try_center':p.update(trial_kind='center',mode='manual',force_trials=True)
    if op=='find_center':p.update(center_only=True,full_requested=False,mode='auto')
    elif op in ('analyze','reconstruct'):p.update(center_only=False,full_requested=True)
    if op=='analyze':p['mode']='auto'
    if 'geometry' in u:p['geometry_confirmed']=True
    if 'lamino_angle' in u:
        if u['lamino_angle']==0:raise ValueError('Provide a signed nonzero lamino angle')
        p.update(angle_confirmed=True,geometry_confirmed=True);s['geometry']='laminography'
    if old_geometry!=s['geometry']:
        p['center_valid']=False;s['center']=u.get('center',0.)
        if 'lamino_angle' not in u:p['angle_confirmed']=False
    if 'center' in u:
        p['center_valid']=op!='try_center' and phase not in ('trial_offer','choose') and not any(k in u for k in ('trial_width','range_low','range_high'))
        if not p.get('mode'):p['mode']='manual'
    is_range=any(k in u for k in ('trial_width','trial_step','range_low','range_high','initial_step'))
    if is_range and p.get('mode')!='auto':
        if 'range_low' in u or 'range_high' in u:
            if s['range_low'] is None or s['range_high'] is None:raise ValueError('Provide both bounds of the search range')
            anchor=(s['range_low']+s['range_high'])/2;s['trial_width']=(s['range_high']-s['range_low'])/2
            s['lamino_angle' if p.get('trial_kind')=='angle' else 'center']=anchor
            s['range_low']=s['range_high']=None
        if 'initial_step' in u:s['trial_step']=u['initial_step'];s['initial_step']=task['settings'].get('initial_step')
        if p.get('trial_kind')!='angle' and s['center']<=0 and draft.get('metadata'):s['center']=(draft['metadata']['width']-1)/2
        p['force_trials']=True;p['center_valid']=p.get('center_valid',False) if p.get('trial_kind')=='angle' else False
        if not p.get('mode'):p['mode']='manual'
    elif is_range and p.get('mode')=='auto':
        if 'trial_width' in u:
            anchor=u.get('center',s['center'])
            if anchor<=0:raise ValueError('Provide the center of the automatic search range')
            s.update(range_low=anchor-u['trial_width'],range_high=anchor+u['trial_width'])
        if 'trial_step' in u:s['initial_step']=u['trial_step']
    if 'start_row' in u or 'end_row' in u:p['explicit_rows']=True;mark(draft,'rows')
    if turn['row_scope']!='unchanged':
        p['model_row_scope']=turn['row_scope'];p['explicit_rows']=turn['row_scope']=='middle'
        if draft.get('metadata'):
            n=draft['metadata']['rows'];s['start_row'],s['end_row']=(0,n) if turn['row_scope']=='all' else (max(0,n//2-2),min(n,n//2+3))
            mark(draft,'rows')
    if 'prompt' in u:
        if not u['prompt'].strip():raise ValueError('The SAM3 feature cannot be empty')
        s['prompt_mode']='text';s['instance_reference']={};p['target_confirmed']=True
    if not draft.get('metadata'):
        # Source dimensions are checked after the metadata read.
        validate_settings(s)
    else:validate_current(draft)
    task['settings'].clear();task['settings'].update(s);task['sop'].clear();task['sop'].update(p);task['done']=draft['done']


def apply_turn(sop,t,text,turn,remote=False):
    from .reconstruction_sop import input_paths,KINDS,fingerprint,estimate
    from .trial_candidates import selection
    from .results import answer_result
    intent,op=turn['intent'],turn['operation']
    if intent in ('explain','clarify'):
        sop.tell(t,turn['message']);return
    if intent=='cancel':
        if t['state'] in ('running','stopping'):sop.w.stop_task(t)
        else:t['cancel_requested']=True;sop.phase(t,'paused');sop.tell(t,'Paused. No computation will start.','已暂停，不会启动计算。')
        return
    if intent=='status':
        if t.get('jobs'):sop.w.show_status(t)
        else:sop.tell(t,'Current planning step: '+t.get('sop',{}).get('phase','path'),'当前准备步骤：'+t.get('sop',{}).get('phase','path'))
        return
    if intent=='result':
        query=turn['query']
        if query=='time' and t.get('sop',{}).get('phase')=='confirm':sop.tell(t,estimate(t));return
        if query=='none':sop.tell(t,turn['message']);return
        answer,path=answer_result(t,query);sop.tell(t,answer)
        if path:
            if remote:
                if Path(path).is_file() and sop.w.telegram.bridge:sop.w.telegram.bridge.send_image(path)
            else:sop.open_folder(t,path)
        return
    if t['state'] in ('running','stopping'):
        sop.tell(t,'This task is running. Ask for progress or stop it before changing parameters.','当前任务正在运行，可以询问进度或先安全停止再修改参数。');return
    sop.bootstrap(t);p=t['sop'];p['remote']=remote;sop.overview(t)
    paths=input_paths(text);h5=[x for x in paths if Path(x).suffix.lower() in ('.h5','.hdf5','.hdf')]
    if op in ('segment','train'):
        handoff(sop,t,text,turn,remote);return
    if len(h5)>1:
        if re.search(r'flat|平场',text,re.I):
            sop.tell(t,'A separate external flat file is not yet supported by this workflow.','当前流程暂不支持单独指定外部平场。');return
        p.update(files=h5,file_turn=copy.deepcopy(turn));sop.phase(t,'file');sop.tell(t,'Please choose one HDF5:\n'+'\n'.join(f'{i}. {x}' for i,x in enumerate(h5,1)));return
    source=turn['updates'].get('input_hdf5') or (h5[0] if len(h5)==1 else '')
    if p['phase']=='file' and intent=='select':
        m=re.search(r'\d+',turn['selection'])
        if not m or not 1<=int(m[0])<=len(p['files']):raise ValueError('Choose one of the displayed file numbers')
        source=p['files'][int(m[0])-1];prior=p.get('file_turn',turn);turn={**prior,'updates':{**prior['updates'],**turn['updates'],'input_hdf5':source}}
    if source:
        existing=p.get('source','');changed=True
        try:stat=Path(source).stat();changed=p.get('source_stat')!=[stat.st_size,stat.st_mtime_ns]
        except OSError:pass
        from .path_rules import path_key
        if changed or path_key(source)!=path_key(existing) or not t.get('metadata'):
            sop._source(t,source,text,remote,understood=turn);return
    if not t.get('metadata'):
        folders=[x for x in paths if Path(x).is_dir()]
        if folders:
            files=sorted(str(x) for x in Path(folders[0]).iterdir() if x.suffix.lower() in ('.h5','.hdf5','.hdf') and x.is_file())
            if len(files)==1:sop._source(t,files[0],text,remote,understood=turn);return
            if files:p.update(files=files,file_turn=copy.deepcopy(turn));sop.phase(t,'file');sop.tell(t,'Choose one HDF5:\n'+'\n'.join(f'{i}. {x}' for i,x in enumerate(files,1)));return
        apply_fields(sop,t,turn);sop.phase(t,'path');sop.tell(t,'Which data should I reconstruct? Please paste the HDF5 path. I will show its file information first.','请提供需要重建的 HDF5 路径，我会先读取并返回文件信息。');return
    if intent=='select' and p['phase'] in ('choose','choose_angle'):
        if not turn['selection']:raise ValueError('Specify one image number, value or saved filename')
        is_angle=p['phase']=='choose_angle';value,error=selection(turn['selection'],p['candidates'],t['metadata']['width'],'angle' if is_angle else 'center')
        if error:raise ValueError(error)
        t['settings']['lamino_angle' if is_angle else 'center']=value;p.update(center_valid=True,force_trials=False,selection=dict(value=value,quantity='angle' if is_angle else 'center',user_text=text))
        if is_angle:p['angle_confirmed']=True
        sop.review(t);return
    if intent=='confirm' and p['phase'] in ('complete','center_ready'):
        sop.tell(t,'No new computation was requested. Tell me whether to reconstruct, inspect results or start another task.','尚未收到新的计算指令。请告诉我是继续重建、查看结果还是开始其他任务。');return
    old_phase=p['phase'];has_edits=bool(turn['updates']) or turn['mode']!='unchanged' or turn['row_scope']!='unchanged'
    apply_fields(sop,t,turn);p=t['sop'];validate_current(t)
    if op=='measure_time':
        if old_phase=='confirm' and not has_edits:sop.handle(t,'measure time',remote)
        else:sop.next(t);sop.tell(t,'Please review the settings first, then ask me to measure time. No timing job has started.','请先核对参数，再告诉我先测时。目前尚未启动测时任务。')
        return
    if intent=='instance':
        p['mode']='manual' if p.get('mode')=='manual' and t['settings'].get('segment_all') else 'auto';p['target_confirmed']=False
        images=[x for x in paths if Path(x).suffix.lower() in ('.png','.tif','.tiff','.jpg','.jpeg','.bmp')]
        sop.phase(t,'instance');sop._instance(t,images,remote);return
    if intent in ('confirm','execute') and not has_edits and old_phase=='confirm':
        # The same file/dependency fingerprint checked by the original SOP still gates execution.
        sop.handle(t,'confirm reconstruction',remote);return
    if intent in ('confirm','execute') and old_phase=='trial_offer':
        sop.launch(t,'angle_trial' if p.get('trial_kind')=='angle' else 'trial');return
    if intent in ('confirm','execute') and old_phase=='search_offer':sop.launch(t,'search');return
    if is_range_edit(turn,p):
        s=t['settings'];anchor=s['lamino_angle'] if p.get('trial_kind')=='angle' else s['center'];unit='degrees' if p.get('trial_kind')=='angle' else 'px'
        if p.get('mode')=='auto':
            low,high=s['range_low'],s['range_high'];step=s['initial_step']
            if low is None:sop.tell(t,f'Updated automatic initial step: {step:g} px. Search bounds remain automatic.',f'自动搜索的初始步长已更新为 {step:g} 像素，搜索范围保持自动。');sop.next(t);return
            anchor=(low+high)/2;radius=(high-low)/2
        else:low,high=anchor-s['trial_width'],anchor+s['trial_width'];step=s['trial_step'];radius=s['trial_width']
        sop.tell(t,f'Updated: {anchor:g} ± {radius:g} {unit}; range {low:g}–{high:g}; step {step:g}. Say generate candidates when ready.',f'已更新：中心 {anchor:g} ± {radius:g} {unit}，范围 {low:g}–{high:g}，步长 {step:g}。准备好后说“生成候选”。')
        if p.get('mode')!='auto':sop.phase(t,'trial_offer');return
    if old_phase in ('paused','interrupted','edit_error') and intent=='confirm':sop.next(t);return
    sop.next(t)


def is_range_edit(turn,p):
    return any(k in turn['updates'] for k in ('trial_width','trial_step','range_low','range_high','initial_step')) and (p.get('force_trials') or p.get('mode')=='auto')


def handoff(sop,t,text,turn,remote):
    from .conversations import choose_kind
    from .results import result_context
    kind=turn['operation'];target=sop.w.repo.create();target['language']=t.get('language','en')
    sop.w.tasks={target['id']:target,**sop.w.tasks};choose_kind(target,kind)
    target['settings'].update(output_root=t['settings']['output_root'],gpu=t['settings']['gpu'])
    target['settings'].update(turn['updates'])
    field='image_folder' if kind=='segment' else 'dataset'
    if kind=='segment' and not target['settings'].get(field):
        for record in reversed(result_context(t)):
            if record.get('state')=='succeeded' and record['action'] in ('reconstruct','analyze'):
                folder=Path(record['output'])/'reconstruction'
                if folder.is_dir():target['settings'][field]=str(folder);break
    sop.w.add(target,'user',text);sop.w.save(target)
    sop.tell(t,'Created a separate '+kind+' task; your reconstruction history is preserved.','已新建'+('分割' if kind=='segment' else '训练')+'任务，当前重建记录保留。')
    if remote:sop.w.telegram.subscribe(target,False)
    else:sop.w.select_task(target['id'])
    if target['settings'].get(field):
        sop.w.add(target,'assistant','');target['reply_id']=target['messages'][-1]['id'];sop.w.inspect(target,field,target['settings'][field])
    else:sop.w.guide(target)
    sop.w.refresh_list()
