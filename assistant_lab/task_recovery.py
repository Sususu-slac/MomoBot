"""Repair old file-URL inputs and restore results only for the selected data."""
from .path_rules import normalize_path,path_key,extract_paths
from .conversations import PATHS
from .answer_bindings import explicit_answer


def recover_task(task,records):
    if task['state'] in ('running','stopping'):return
    settings=task['settings'];old=settings.get('input_hdf5','')
    for field in PATHS:
        if settings.get(field):settings[field]=normalize_path(settings[field])
    if old.casefold().startswith('file:') and not task['metadata'] and 'input_hdf5' not in task['done']:
        # Older versions copied a previous file's center into a failed file-URL request.
        command=next((m['text'] for m in reversed(task['messages']) if m['role']=='user' and any(path_key(p)==path_key(old) for p in extract_paths(m['text']))),'')
        binding_task={**task,'state':'draft'};bindings,_=explicit_answer(command,binding_task)
        settings['center']=bindings.get('center',0.0);task['center_mode']='known' if settings['center']>0 else None
        task['done']=[key for key in task['done'] if key not in ('rows','center','prompt')]
        task['prompt_confirmed']=False;task['run_requested']=False
        for name in ('start_row','end_row'):
            if name in bindings:settings[name]=bindings[name]
        if any(name in bindings for name in ('start_row','end_row')):task['done'].append('rows')
    source=settings.get('input_hdf5','')
    if source and settings['center']<=0:
        record=next((r for r in reversed(records) if r.get('recommended_center') is not None and r.get('source') and path_key(r['source'])==path_key(source)),None)
        if record:settings['center']=float(record['recommended_center']);task['center_mode']='known'
    # New work follows the user's GPU assignment; archived job configs remain factual.
    settings['gpu']=0
