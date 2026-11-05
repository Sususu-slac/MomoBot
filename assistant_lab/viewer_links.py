"""Task-bound desktop viewer links. Model prose is never treated as a URL or command."""
from __future__ import annotations
import copy,uuid
from pathlib import Path
from .jobs import read_json
from .path_rules import path_key
from .data_viewers import InputBrowser,ResultBrowser,file_stamp


def attach_tool(window,task,kind,source,job=None,entry=None,render=True):
    entry=entry or task['messages'][-1]
    tools=entry.setdefault('tools',[]);job_id=job['id'] if job else None
    if any(x['kind']==kind and x['source']==str(source) and x.get('job_id')==job_id for x in tools):return
    labels={'input':'View data / Set parameters','trials':'Review trial images / Select parameter','results':'Browse reconstruction'}
    cfg=read_json(Path(job['job_dir'])/'job.json') if job else {}
    input_source=cfg.get('settings',{}).get('input_hdf5') or task['settings']['input_hdf5']
    stamp=cfg.get('source_stat') or (job or {}).get('source_stat') or (task.get('sop',{}).get('source_stat') if path_key(input_source)==path_key(task['settings']['input_hdf5']) else None)
    tools.append(dict(id=uuid.uuid4().hex,kind=kind,label=labels[kind],source=str(source),input_source=input_source,source_stat=copy.deepcopy(stamp),metadata=copy.deepcopy(task.get('metadata',{})),job_id=job_id))
    if kind=='input':
        keys=('geometry','lamino_angle','method','center','start_row','end_row','binning','gpu','search_row','trial_row','trial_width','trial_step','prompt','prompt_mode','remove_stripe_method','dezinger')
        tools[-1]['parameters']={k:copy.deepcopy(task['settings'][k]) for k in keys if k in task['settings']}
        tools[-1]['workflow']={k:task.get('sop',{}).get(k) for k in ('geometry_confirmed','angle_confirmed','mode','target_confirmed')}
    window.save(task)
    if render:window.render_if_current(task)


def current_source(task,tool):
    return path_key(task['settings']['input_hdf5'])==path_key(tool['input_source']) and task.get('sop',{}).get('source_stat')==tool['source_stat']


def writable(window,task,tool):
    if task.get('_deleted') or task['id'] not in window.tasks:raise ValueError('This task was deleted.')
    if window.closing or window.busy or task['state'] in ('running','stopping'):raise ValueError('Wait for the current operation before changing parameters.')
    if not current_source(task,tool):raise ValueError('This viewer belongs to a different input. Open the current input link.')
    if file_stamp(tool['input_source'])!=tool['source_stat']:raise ValueError('The input file changed. Reload it in MomoBot first.')


def apply_input(window,task,tool,payload):
    from .reconstruction_turns import apply_fields,validate_current
    writable(window,task,tool)
    turn=dict(intent='configure',operation='unchanged',mode=payload['mode'],row_scope='unchanged',updates=payload['updates'],selection='',query='none',message='')
    draft=copy.deepcopy(task)
    try:apply_fields(window.sop,draft,turn);validate_current(draft)
    except (ValueError,KeyError) as error:
        window.sop.reject(task,str(error));raise
    # Commit only after the entire edited draft has passed the same SOP validation.
    task['settings']=draft['settings'];task['sop']=draft['sop'];task['done']=draft['done'];task['sop'].pop('review_fingerprint',None)
    window.select_task(task['id']);details=', '.join(f'{k}={v}' for k,v in turn['updates'].items())
    if turn['mode']!='unchanged':details+=f", workflow={turn['mode']}"
    window.add(task,'user','Applied from Data Viewer: '+details);window.sop.next(task);window.save(task)


def apply_candidate(window,task,tool,item):
    from .reconstruction_turns import apply_turn
    writable(window,task,tool)
    if task.get('sop',{}).get('phase') not in ('choose','choose_angle'):raise ValueError('This trial selection is no longer pending. The viewer remains available for browsing.')
    candidates=task['sop'].get('candidates',[])
    match=next((x for x in candidates if x['index']==item['index'] and x['value']==item['value'] and path_key(x['file'])==path_key(item['file'])),None)
    trials=[j for j in task['jobs'] if j['action'] in ('try_center','try_angle')]
    if not match or not trials or trials[-1]['id']!=tool['job_id']:raise ValueError('These are older trial results. Open the latest trial link to select a parameter.')
    if not Path(item['file']).is_file():raise ValueError('The selected candidate file is missing.')
    window.select_task(task['id']);text=f"Selected candidate {item['index']}: {item['quantity']} {item['value']:g} from Trial Viewer."
    window.add(task,'user',text)
    turn=dict(intent='select',operation='unchanged',mode='unchanged',row_scope='unchanged',updates={},selection='candidate '+str(item['index']),query='none',message='')
    apply_turn(window.sop,task,text,turn);window.save(task)


def open_tool(window,identity,entry_id,tool_id):
    task=window.tasks.get(identity)
    if not task or task.get('_deleted'):return None
    entry=next((x for x in task['messages'] if x['id']==entry_id and x['role']=='assistant'),None)
    tool=next((x for x in (entry or {}).get('tools',[]) if x.get('id')==tool_id),None)
    if not tool:return None
    key=(identity,tool['kind'],tool.get('job_id') or tool['source'])
    existing=window.viewer_windows.get(key)
    if existing is not None:existing.showNormal();existing.raise_();existing.activateWindow();return existing
    try:
        if tool['kind']=='input':
            if file_stamp(tool['source'])!=tool['source_stat']:raise ValueError('The input changed. Send its path again to load its current metadata.')
            snapshot=copy.deepcopy(task);snapshot['metadata']=tool['metadata']
            if not current_source(task,tool):snapshot['settings'].update(tool.get('parameters',{}));snapshot.setdefault('sop',{}).update(tool.get('workflow',{}))
            dialog=InputBrowser(window,snapshot,tool)
            def applied(payload):
                try:apply_input(window,task,tool,payload);dialog.accept()
                except (ValueError,OSError,KeyError) as error:dialog.show_feedback(str(error),True)
            dialog.apply_requested.connect(applied)
            if not current_source(task,tool):dialog.apply_button.setEnabled(False);dialog.show_feedback('Historical input: browsing only. Parameters belong to the current input.')
        elif tool['kind'] in ('trials','results'):
            job=next((j for j in task['jobs'] if j['id']==tool['job_id']),None)
            if not job:raise ValueError('The saved job for this link is no longer available.')
            cfg=read_json(Path(job['job_dir'])/'job.json')
            if cfg.get('id')!=job['id']:raise ValueError('The saved job does not match this link.')
            if path_key(cfg.get('settings',{}).get('input_hdf5',''))!=path_key(tool['input_source']):raise ValueError('The saved result belongs to another input.')
            status=read_json(Path(job['job_dir'])/'job_status.json');result=status.get('result') or read_json(Path(job['job_dir'])/'results/result.json')
            items=result.get('candidate_catalogue',[]) if tool['kind']=='trials' else None
            if tool['kind']=='trials' and not items:
                from .trial_candidates import catalogue
                items=catalogue(result.get('files',[]))
                if not items:raise ValueError('No trial candidate catalogue is available.')
            if job['action']=='try_angle':items=[{**item,'quantity':'angle'} for item in items]
            dialog=ResultBrowser(window,tool,items)
            if tool['kind']=='trials':dialog.can_select=current_source(task,tool) and task.get('sop',{}).get('phase') in ('choose','choose_angle') and next((j['id'] for j in reversed(task['jobs']) if j['action'] in ('try_center','try_angle')),None)==tool['job_id']
            if tool['kind']=='trials' and not dialog.can_select:dialog.use_button.setToolTip('Browsing only: this trial is not the current pending selection. Open the latest trial link to select a parameter.')
            def selected(item):
                try:apply_candidate(window,task,tool,item);dialog.accept()
                except (ValueError,OSError,KeyError) as error:dialog.show_feedback(str(error),True)
            dialog.select_requested.connect(selected)
        else:return None
    except (ValueError,OSError,KeyError) as error:
        window.statusBar().showMessage(str(error),15000);return None
    window.viewer_windows[key]=dialog;dialog.destroyed.connect(lambda:window.viewer_windows.pop(key,None));dialog.show();return dialog


def ensure_tools(window,task):
    """Add entry links lazily when opening an older saved conversation."""
    assistants=[m for m in task['messages'] if m['role']=='assistant']
    if not assistants:return
    meta=task.get('metadata',{});source=task['settings'].get('input_hdf5')
    if source and all(k in meta for k in ('rows','width','projections')) and task.get('sop',{}).get('source_stat'):
        entry=next((m for m in reversed(assistants) if m['text'].startswith('HDF5:')),assistants[-1]);attach_tool(window,task,'input',source,entry=entry,render=False)
    for job in task['jobs']:
        folder=Path(job['job_dir']);status=read_json(folder/'job_status.json');result=status.get('result') or read_json(folder/'results/result.json')
        entry=next((m for m in assistants if m['id']==job.get('reply_id')),assistants[-1])
        if job['action'] in ('try_center','try_angle') and status.get('state')=='succeeded' and (result.get('candidate_catalogue') or result.get('files')):
            attach_tool(window,task,'trials',result.get('preview_folder') or result.get('folder',str(folder/'results/trial_reconstructions')),job,entry,render=False)
        elif job['action'] in ('reconstruct','analyze') and (folder/'results/reconstruction').is_dir():
            attach_tool(window,task,'results',folder/'results/reconstruction',job,entry,render=False)
