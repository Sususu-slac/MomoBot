"""Map actual saved trial filenames to a stable, one-based visual catalogue."""
import csv,re
from pathlib import Path

def catalogue(files,preview_folder=None,check=None):
    items=[]
    for file in files:
        p=Path(file);m=re.search(r'_(center|angle)(-?\d+(?:\.\d+)?)',p.stem,re.I)
        if not m:raise ValueError('Cannot read the candidate value from '+p.name)
        items.append(dict(value=float(m[2]),file=str(p.resolve()),quantity=m[1].lower()))
    items.sort(key=lambda x:(x['value'],x['file']))
    if len({x['value'] for x in items})!=len(items):raise ValueError('Duplicate candidate values; please select an exact filename')
    for index,item in enumerate(items,1):item['index']=index
    if preview_folder:
        import numpy as np,tifffile
        from PIL import Image
        folder=Path(preview_folder);folder.mkdir(exist_ok=True)
        for item in items:
            if check:check()
            a=tifffile.imread(item['file']);a=a[::max(1,a.shape[0]//512),::max(1,a.shape[1]//512)]
            finite=a[np.isfinite(a)]
            if not finite.size:raise ValueError('Candidate contains no finite pixels')
            lo,hi=np.percentile(finite,(1,99.9));gray=np.nan_to_num(np.clip((a-lo)/max(float(hi-lo),1e-12),0,1))*255
            target=folder/f"{item['index']:04d}_{item['quantity']}_{item['value']:.2f}.png"
            Image.fromarray(gray.astype('uint8')).save(target);item['preview']=str(target.resolve())
        with (folder/'candidate_index.csv').open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=['index','value','file','quantity','preview']);writer.writeheader();writer.writerows(items)
    return items

CHINESE={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
def ordinal_number(text):
    if text.isdigit():return int(text)
    if text in CHINESE:return CHINESE[text]
    if '十' in text:
        a,b=text.split('十',1)
        if (not a or a in CHINESE) and (not b or b in CHINESE):return CHINESE.get(a,1)*10+CHINESE.get(b,0)
    return None

def selection(text,items,width,quantity='center'):
    """Return a verified center or a clarification; never infer a visual judgement."""
    value=text.strip();low=value.lower()
    # Match actual filename/preview names first, including pasted full paths.
    matches=[x for x in items if any(Path(x[k]).name.casefold() in low for k in ('file','preview') if x.get(k))]
    if not items:return None,'No saved candidates are available; generate trials first.'
    if len(matches)>1:return None,'Please choose one candidate, not multiple filenames.'
    if len(re.findall(r'\d+(?:\.\d+)?',low))>1 and re.search(r'\bor\b|\band\b|或者|还是|或',low):return None,'Please choose one candidate; your answer mentions alternatives.'
    if len(matches)==1:return matches[0]['value'],None
    ordinals=re.findall(r'第\s*[\d一二三四五六七八九十两]+|(?:image|candidate|#)\s*\d+|\b\d+(?:st|nd|rd|th)\b',low)
    if len(ordinals)>1:return None,'Please select one candidate, not multiple image numbers.'
    if re.search(r'last(?:\s+(?:one|image|candidate))?|最后(?:一)?(?:张|个)',low):return items[-1]['value'],None
    if re.fullmatch(r'(?:the\s+)?(?:middle|中间(?:那)?张)',low):
        if len(items)%2:return items[len(items)//2]['value'],None
        return None,'There are two middle candidates. Please give their number or center value.'
    words={'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6,'seventh':7,'eighth':8,'ninth':9,'tenth':10}
    for word,index in words.items():
        if re.search(r'\b'+word+r'\b',low):
            return (items[index-1]['value'],None) if index<=len(items) else (None,'That candidate number is outside the saved list.')
    m=re.search(r'第\s*([\d一二三四五六七八九十两]+)\s*(?:张|个|幅)?|(?:image|candidate|number|no\.?|#)\s*(\d+)|\b(\d+)(?:st|nd|rd|th)\b',low)
    if m:
        number=ordinal_number(next(x for x in m.groups() if x))
        if number is not None and 1<=number<=len(items):return items[number-1]['value'],None
        return None,f'Please choose a candidate number from 1 to {len(items)}.'
    m=re.search(r'(?:cent(?:er|re)|中心|angle|角度)\s*(?:is|=|:|为|是)?\s*(-?\d+(?:\.\d+)?)',low)
    if not m:
        numbers=re.findall(r'(?<![\w.])(-?\d+(?:\.\d+)?)(?![\w.])',low)
        if len(numbers)==1 and low.strip()!=numbers[0]:return selection(numbers[0],items,width,quantity)
    if not m:m=re.fullmatch(r'\s*(-?\d+(?:\.\d+)?)\s*(?:px|pixels?|像素|degrees?|度|°)?\s*',low)
    if m:
        number=float(m[1]);as_index=number.is_integer() and 1<=number<=len(items)
        as_value=any(abs(number-x['value'])<1e-6 for x in items)
        explicit=bool(re.search(r'center|centre|中心|px|pixels|像素|angle|角度|degrees?|度|°',low))
        if not explicit and as_index:
            chosen=items[int(number)-1]['value']
            if as_value and chosen!=number:return None,f'Do you mean center {number:g} pixels, or candidate {int(number)} (center {chosen:g})?'
            return chosen,None
        if (quantity=='angle' and -89.9<=number<=89.9) or (quantity!='angle' and 0<number<width):return number,None
        return None,('The angle must be between -89.9 and 89.9 degrees.' if quantity=='angle' else f'The center must be greater than 0 and below {width} pixels.')
    return None,'Please give a center value, an image number (for example “candidate 3”), or the saved filename. I cannot identify “the sharpest one” without knowing which image you selected.'
