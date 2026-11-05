"""Bind unambiguous form answers to the same values as the visible choices."""
import re
from .conversations import step
from .path_rules import text_without_paths

def explicit_center(text):
    text=text_without_paths(text)
    match=re.search(r'\b(?:rotation\s+)?cent(?:er|re)\b\s*(?:to|is|of|=|:)?\s*(-?\d+(?:\.\d+)?)|(?:旋转)?中心\s*(?:为|是|设为|设置为|[:：=])?\s*(-?\d+(?:\.\d+)?)',text,re.I)
    return float(next(v for v in match.groups() if v is not None)) if match else None

def explicit_answer(text,task):
    if task['state'] in ('running','stopping','completed'):return {},{}
    text=text_without_paths(text)
    current=step(task);short=text.lower().strip(' .!');updates={};controls={}
    if re.match(r'^(what|why|how|explain|tell me about)\b',short):return updates,controls
    if current=='rows' or task['kind'] in ('reconstruct','analyze'):
        if short in ('all','all slices','all rows','all slices please','all rows please','all of them'):controls['row_scope']='all'
        elif short in ('middle','middle five','middle 5','five middle slices','five middle slices please','5 middle slices','try five middle slices'):controls['row_scope']='middle'
    if current=='center_mode' and short in ('auto','automatic','automatically','find automatically','find the center automatically','find it automatically'):controls['center_mode']='auto'
    if current in ('epochs','prompt','limit','split') and short in ('default','use default','use the default','keep the default','use defaults'):controls['accept_defaults']=True
    if task['kind'] in ('try_center','try_angle') and re.search(r'\bmiddle\s+(?:detector\s+)?(?:slice|row)\b|中间(?:的)?(?:一)?层',text,re.I):
        # Keep the user's literal "middle" choice, independent of a model's numeric guess.
        updates['trial_row']=None
    if task['kind'] in ('reconstruct','analyze','find_center','try_center','try_angle'):
        # A literal requested geometry must replace the previous task's mode.
        # Paths are already stripped; directory names cannot select geometry.
        geometry_names={'tomo':'tomography','tomography':'tomography','lamino':'laminography','laminography':'laminography'}
        named=set()
        for match in re.finditer(r'\b(?:tomography|tomo|laminography|lamino)\b(?!\s+(?:angle|tilt)\b)',text,re.I):
            prefix=text[max(0,match.start()-35):match.start()]
            if re.search(r"(?:\b(?:not|no|never|avoid|disable)\s+(?:(?:use|using|a|an)\s+)?|\b(?:do\s+not|don't)\s+(?:use\s+|using\s+)?|(?:不要|不用|非)\s*)$",prefix,re.I):continue
            named.add(geometry_names[match.group(0).lower()])
        if len(named)==1:updates['geometry']=named.pop()
        # Explicit detector binning wins over a model's guessed exponent.
        factor=None
        for pattern in (r'\b([1248])\s*[x×*]\s*\1\s*(?:binning|bin\b|合并)',
                        r'(?:\bbinning\b|合并)\s*(?:to|is|=|:|为|是|[:：])?\s*([1248])\s*[x×*]\s*\1\b'):
            match=re.search(pattern,text,re.I)
            if match:factor=int(match[1]);break
        if factor is not None:updates['binning']={1:0,2:1,4:2,8:3}[factor]
    patterns={
      'gpu':r'\bgpu\s*(?:to|is|=|:)?\s*(\d+)\b',
      'epochs':r'\b(\d+)\s*epochs?\b',
      'batch_size':r'\bbatch(?:\s+size)?\s*(?:to|is|=|:)?\s*(\d+)\b',
      'workers':r'\b(\d+)\s*(?:data\s+)?workers?\b',
      'seed':r'\bseed\s*(?:to|is|=|:)?\s*(\d+)\b',
      'start_row':r'\bstart\s+row\s*(?:to|is|=|:)?\s*(\d+)\b',
      'end_row':r'\bend\s+row\s*(?:to|is|=|:)?\s*(\d+)\b',
      'max_images':r'\b(?:only|first)\s+(\d+)\s*(?:images?|pictures?)\b',
      'confidence':r'\bconfidence(?:\s+threshold)?\s*(?:to|is|of|=|:)?\s*(\d+(?:\.\d+)?)\s*(%|percent)?',
      'train_percent':r'\b(\d+)\s*%\s*(?:for\s+)?train(?:ing)?\b'}
    allowed={'gpu'}
    center=explicit_center(text)
    if center is not None and task['kind'] in ('reconstruct','analyze','find_center','try_center','try_angle'):
        updates['center']=center
    if task['kind']=='segment':allowed|={'confidence','max_images'}
    if task['kind'] in ('train','prepare_dataset'):allowed|={'epochs','batch_size','workers','seed','train_percent'}
    if task['kind'] in ('reconstruct','analyze'):allowed|={'start_row','end_row'}
    for key,pattern in patterns.items():
        if key not in allowed:continue
        match=re.search(pattern,short)
        if match:
            updates[key]=float(match[1])/(100 if match[2] else 1) if key=='confidence' else int(match[1])
    if task['kind']=='segment':
        match=re.search(r'前\s*(\d+)\s*张',text)
        if match:updates['max_images']=int(match[1])
        match=re.search(r'置信度\s*(\d+(?:\.\d+)?)\s*(%|％)?',text)
        if match:updates['confidence']=float(match[1])/(100 if match[2] else 1)
    if current in ('center','epochs','limit') and re.fullmatch(r'\d+(?:\.\d+)?',short):updates[{'center':'center','epochs':'epochs','limit':'max_images'}[current]]=float(short) if current=='center' else int(short)
    if current=='limit' and short in ('all','all images','all pictures'):updates['max_images']=0
    return updates,controls
