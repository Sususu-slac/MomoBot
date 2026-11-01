"""Conversation-first task policy: inspect inputs, fill defaults, then execute requests."""
from pathlib import Path
import re
from .path_rules import extract_paths,normalize_path,path_key
from .conversations import step,mark,action,review

def chinese(text):return bool(re.search(r'[\u3400-\u9fff]',text))
def say(task,en,zh):return zh if task.get('language')=='zh' else en

def execution_intent(text,awaiting=False):
    lower=text.lower().strip(' .!。！')
    if re.search(r"\b(how|what|why|explain|discuss)\b|don't (?:run|start)|do not (?:run|start)|not yet|怎么|如何|是什么|解释|先讨论|不要运行|先不运行|别运行",lower):return False
    if lower in ('start','run','go ahead','start now','开始','开始吧','执行','执行吧','运行','运行吧'):return True
    if awaiting and lower in ('yes','okay','ok','sure','proceed','好的','可以','确认','确认执行'):return True
    return bool(re.search(r'\b(reconstruct|recon|segment|train|fine[- ]?tune|prepare|split|generate|sweep|jitter)\b|\bfind\b.{0,25}\bcent(?:er|re)\b|重建|分割|训练|微调|划分|找(?:旋转)?中心|抖动|生成候选',lower))

def source_field(task):
    return 'image_folder' if task['kind']=='segment' else 'dataset' if task['kind'] in ('train','prepare_dataset') else 'input_hdf5'

def bind_paths(task,plan,text):
    paths=extract_paths(text)
    if not paths:return
    for value in paths:
        suffix=Path(value).suffix.lower()
        field='checkpoint' if suffix in ('.pt','.pth') else 'input_hdf5' if suffix in ('.h5','.hdf5','.hdf') else 'dataset' if suffix=='.json' else source_field(task) if task['kind'] else None
        if field:
            for other in ('input_hdf5','image_folder','dataset'):
                if other!=field and other in plan.updates and plan.updates[other].replace('\\','/').casefold()==value.replace('\\','/').casefold():del plan.updates[other]
            if field not in plan.updates:plan.updates[field]=value

def apply_defaults(task):
    if not task['kind']:return
    s=task['settings'];meta=task['metadata'];done=task['done']
    if task['kind'] in ('reconstruct','analyze'):
        if not task.get('center_mode'):task['center_mode']='known' if s['center']>0 or s['geometry']=='laminography' else 'auto'
        if meta.get('rows') and 'input_hdf5' in done and 'rows' not in done:
            n=meta['rows'];scope=task.pop('requested_scope','all')
            s['start_row'],s['end_row']=(max(0,n//2-2),min(n,n//2+3)) if scope=='middle' else (0,n)
            mark(task,'rows')
    automatic=task['kind'] in ('find_center','analyze') or task.get('center_mode')=='auto'
    if not automatic:mark(task,'prompt')
    mark(task,'limit','split','epochs')
    if task['kind'] in ('try_center','try_angle'):
        if task['kind']=='try_angle':s['geometry']='laminography';s['method']='linerec'
        elif s['geometry']=='laminography':s['method']='linerec'

def ready_step(task):
    apply_defaults(task)
    if task['state'] in ('running','stopping'):return 'running'
    if not task['kind']:return 'kind'
    if source_field(task) not in task['done']:return source_field(task)
    if task['kind']=='try_angle' and task['settings']['center']<=0:return 'center'
    if task['kind']=='find_center' and task.get('search_mode') is None:return 'search_mode'
    if (task['kind'] in ('find_center','analyze') or task.get('center_mode')=='auto') and not task.get('prompt_confirmed'):return 'prompt'
    return step(task)

def guidance(task):
    current=ready_step(task)
    if current=='kind':return say(task,'Tell me what you would like to do and paste the data path. For example: reconstruct a dataset, segment images, or fine-tune a model.','告诉我想做什么，并直接粘贴数据路径即可。例如重建数据、分割图片或微调模型。')
    if current=='input_hdf5':return say(task,'Please paste the HDF5 file path. I will inspect the data and handle the reconstruction settings.','请直接粘贴 HDF5 文件路径。我会检查数据并配置重建参数。')
    if current=='image_folder':return say(task,'Please paste the image folder path. I will check the images and use the current particle prompt unless you specify another target.','请粘贴图片文件夹路径。我会检查图片；识别目标默认使用 particle，也可以直接告诉我其他目标。')
    if current=='dataset':return say(task,'Please paste the saved training dataset folder or the COCO JSON path. I can prepare the train/validation split if needed.','请粘贴训练数据集文件夹或 COCO JSON 的路径。需要时我会先准备训练和验证数据。')
    if current=='center':return say(task,'You chose a known rotation center. What is its value in pixels?','你指定使用已有旋转中心，请告诉我中心值是多少像素。')
    if current=='search_mode':return say(task,'Should I generate trial reconstructions for you to choose from, or automatically score them with SAM3?','这次是生成一组试重建让你挑选，还是用 SAM3 自动评分找中心？')
    if current=='prompt':return say(task,'What feature should I look for when scoring the reconstructions? For example, particle.','自动评分时，你想找什么 feature？例如 particle（颗粒）。')
    if current=='ready':return review(task)+'\n'+say(task,'Tell me to start when you want me to run it.','准备好后直接回复“开始”即可执行。')
    if current=='running':return say(task,'The task is running. You can ask about progress or tell me to stop.','任务正在运行，可以直接询问进度，或告诉我停止。')
    return say(task,'The task is complete. Tell me what you would like to do next.','任务已完成。接下来想做什么，直接告诉我即可。')

def resolve_source(field,value):
    """Resolve an explicitly selected folder, never search outside it."""
    p=Path(value)
    if field=='input_hdf5' and p.is_dir():
        candidates=[f for f in p.iterdir() if f.is_file() and f.suffix.lower() in ('.h5','.hdf5','.hdf')]
        if len(candidates)==1:return str(candidates[0])
        raise ValueError('Please provide one HDF5 file path; this folder does not contain exactly one HDF5 file.')
    if field=='image_folder' and p.is_file() and p.suffix.lower() in ('.png','.tif','.tiff','.jpg','.jpeg','.bmp'):
        raise ValueError('Please provide the image folder path. Individual-image selection is not available in this backend yet.')
    return value

def find_entry(task,identity):return next((m for m in task['messages'] if m['id']==identity),None)

def activity(task,identity,text,state='working',done=0,total=0):
    entry=find_entry(task,identity)
    if not entry:return
    events=entry.setdefault('activity',[])
    if not events or events[-1]['text']!=text:
        if events and events[-1]['state']=='working':events[-1]['state']='done'
        events.append(dict(text=text,state=state))
    else:events[-1]['state']=state
    entry['progress']=dict(state=state,done=done,total=total)

def finish_activity(task,identity,state='done'):
    entry=find_entry(task,identity)
    if entry:
        for event in entry.get('activity',[]):
            if event['state']=='working':event['state']=state
        entry['progress']=dict(state=state,done=1,total=1)
