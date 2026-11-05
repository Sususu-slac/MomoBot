"""Persistent reconstruction guidance. Scientific dispatch is gated independently of LLM prose."""
from __future__ import annotations
import copy,hashlib,json,re,sys,time,uuid
from pathlib import Path
from .config import DEFAULTS,STATE_ROOT,RECON
from .conversations import choose_kind,mark,inspect_source
from .answer_bindings import explicit_answer
from .path_rules import extract_paths,path_key,text_without_paths,normalize_path
from .chat_flow import say
from .jobs import read_json
from .trial_candidates import catalogue,selection

H5_LITERAL=r'(?:[A-Za-z]:[\\/]|/mnt/[A-Za-z]/)[^\n\r"<>]*?\.(?:hdf5|h5|hdf)(?=\s|$|["，。]|[.,;!?])'
def input_paths(text):
    full=[normalize_path(m[0]) for m in re.finditer(H5_LITERAL,text,re.I)]
    return full+[p for p in extract_paths(text) if not any(path_key(p)==path_key(f) or path_key(f).startswith(path_key(p)+' ') for f in full)]
def clean_text(text):return text_without_paths(re.sub(H5_LITERAL,' ',text,flags=re.I))

KINDS={'reconstruct','analyze','find_center','try_center','try_angle'}
CONFIRM={'go ahead','proceed','确认执行','开始吧','yes','ok','okay','start','run','confirm','确认','好的','可以','开始','confirm reconstruction','confirm full reconstruction','start full reconstruction','确认重建','确认全量重建','开始全量重建'}

def fingerprint(task):
    s=task['settings'];p=Path(s['input_hdf5']);stat=p.stat()
    dependencies={}
    for key,value in ({'checkpoint':s.get('checkpoint',''),**(s.get('instance_reference',{}) if s.get('prompt_mode')=='instance' else {})}).items():
        dependency=Path(value)
        dependencies[key]=[dependency.stat().st_size,dependency.stat().st_mtime_ns] if dependency.is_file() else None
    payload=dict(settings=s,source=[str(p.resolve()),stat.st_size,stat.st_mtime_ns],dependencies=dependencies)
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

def confirmation(text):
    return text in CONFIRM or bool(re.fullmatch(r'(?:yes|ok|okay)[,!， ]*(?:please )?(?:go ahead|proceed|start|run)(?: (?:the )?(?:full )?reconstruction)?|(?:yes|ok|okay) please|(?:好的|可以|确认)[，, ]*(?:开始|执行|重建|开始重建|开始全量重建)',text,re.I))

def timing_key(task):
    s=task['settings'];path=Path(s['input_hdf5']);stat=path.stat()
    keys=('geometry','method','binning','gpu','remove_stripe_method','dezinger','dezinger_threshold','filter_name','bright_ratio','minus_log','flat_linear','chunk_size')
    payload={k:s.get(k) for k in keys};payload.update(source=[str(path.resolve()),stat.st_size,stat.st_mtime_ns],lamino_angle=s['lamino_angle'] if s['geometry']=='laminography' else 0)
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

def human_time(seconds):
    if seconds<90:return f'{seconds:.0f} s'
    if seconds<7200:return f'{seconds/60:.0f} min'
    return f'{seconds/3600:.1f} h'

def estimate(task):
    s=task['settings'];count=(s['end_row']-s['start_row'])//2**s['binning']
    for sample in reversed(read_json(STATE_ROOT/'reconstruction_timings.json',[])+task.get('sop',{}).get('timings',[])):
        if sample.get('key')==timing_key(task):
            ratio=count/max(1,sample['slices']);base=sample['seconds']
            low=max(base*.5,base*ratio*.35);high=max(base*2,base*ratio*2.5)
            return say(task,f'Estimated time: {human_time(low)}–{human_time(high)} (extrapolated from this data; includes shared-I/O uncertainty).',f'预计耗时：{human_time(low)}–{human_time(high)}（根据本数据测时外推，包含读取和计算的不确定性）。')
    return say(task,'Estimated time: no matching measurement yet, so a reliable number is unavailable. Say “measure time” to reconstruct a few middle slices first; I will then estimate the full run.', '预计耗时：暂无同数据、同设置的测时，暂时不能可靠给数。回复“先测时”可先重建几层，再估算全量时间。')

class ReconstructionSOP:
    def __init__(self,window):self.w=window
    def tell(self,t,en,zh=None):
        self.w.add(t,'assistant',say(t,en,zh or en));t['reply_id']=t['messages'][-1]['id'];self.w.save(t);self.w.refresh_list();self.w.render_if_current(t)
    def phase(self,t,name):t['sop']['phase']=name;t['awaiting_confirmation']=False;t['run_requested']=False;self.w.save(t)
    def enabled(self,t):return bool(t.get('sop',{}).get('enabled'))
    def bootstrap(self,t):
        if self.enabled(t):return
        t['sop']=dict(enabled=True,phase='path',geometry_confirmed=False,angle_confirmed=False,mode=None,source='',candidates=[],timings=[])
    def _parameters(self,t,text):
        # Parse atomically: a rejected edit cannot partly mutate a confirmed plan.
        draft=copy.deepcopy(t)
        changes=self._parse_parameters(draft,text)
        t['settings'].clear();t['settings'].update(draft['settings'])
        t['sop'].clear();t['sop'].update(draft['sop'])
        return changes
    def _parse_parameters(self,t,text):
        clean=clean_text(text)
        if re.search(r'(?:gpu|start row|end row|step|步长)\s*(?:[:=]|to|is)?\s*-\d',clean,re.I):raise ValueError('GPU, row indices and step must be nonnegative; step must be positive')
        for b in re.finditer(r'(\d+)\s*[x×]\s*\1\s*(?:binning|合并)',clean,re.I):
            if int(b[1]) not in (1,2,4,8):raise ValueError('Supported binning: 1x1, 2x2, 4x4 or 8x8')
        draft={**t,'kind':'reconstruct','state':'draft'};changes,_=explicit_answer(clean,draft)
        for key in ('geometry','center','binning','gpu','start_row','end_row'):
            if key in changes:t['settings'][key]=changes[key]
        if 'geometry' in changes:t['sop']['geometry_confirmed']=True
        if changes.get('center',0)>0:
            t['sop']['center_valid']=True
            if not t['sop'].get('mode'):t['sop']['mode']='manual'
        no_full=bool(re.search(r'only.*(?:center|search)|(?:do not|don.t|without|no)\s+(?:full\s+)?recon|只(?:找|寻找|查找).*中心|仅.*中心|(?:不要|不做|先不).*重建',clean,re.I))
        if no_full:t['sop'].update(center_only=True,full_requested=False)
        elif re.search(r'\brecon(?:struct(?:ion)?)?\b|重建',clean,re.I):t['sop'].update(full_requested=True,center_only=False)
        if 'center' in changes and not 0<changes['center']<t.get('metadata',{}).get('width',float('inf')):raise ValueError('Center must be positive and inside the detector width')
        rows=re.search(r'(?:rows?|层范围)\s*[:：=]?\s*(\d+)\s*(?:to|[-–]|到|至)\s*(\d+)',clean,re.I)
        if rows:
            a,b=map(int,rows.groups());t['settings'].update(start_row=a,end_row=b);changes.update(start_row=a,end_row=b)
        if re.search(r'(?:do not|don.t|no|without)\s+(?:any\s+)?segmen|不(?:要)?分割|不做分割',clean,re.I):t['settings']['segment_all']=False;changes['segment_all']=False
        elif re.search(r'\bsegment\s+all\b|分割全部|全部分割',clean,re.I):t['settings']['segment_all']=True;changes['segment_all']=True
        m=re.search(r'(?:lamino(?:graphy)?\s*(?:tilt\s*)?angle|tilt\s*angle|倾斜角(?:度)?|倾角)\s*(?:is|=|:|为|是)?\s*(-?\d+(?:\.\d+)?)',clean,re.I)
        if m:
            angle=float(m[1])
            if not -89.9<=angle<=89.9 or angle==0:raise ValueError('Lamino angle must be between -89.9 and 89.9 degrees')
            t['settings']['lamino_angle']=angle;t['sop']['angle_confirmed']=True;changes['lamino_angle']=angle
            if changes.get('geometry')=='tomography':raise ValueError('A laminography tilt angle conflicts with explicit tomography geometry')
            t['settings']['geometry']='laminography';t['sop']['geometry_confirmed']=True;changes['geometry']='laminography'
        for method,pattern in [('fourierrec',r'\bfourier(?:rec)?\b'),('linerec',r'\bline(?:rec)?\b'),('fbp_cuda',r'\bfbp(?:_cuda)?\b'),('sirt_cuda',r'\bsirt(?:_cuda)?\b'),('cgls_cuda',r'\bcgls(?:_cuda)?\b'),('lprec',r'\blprec\b')]:
            if re.search(pattern,clean,re.I):t['settings']['method']=method;changes['method']=method
        if 'start_row' in changes or 'end_row' in changes:t['sop']['explicit_rows']=True
        if not any(k in changes for k in ('start_row','end_row')) and re.search(r'\ball\s+(?:rows|slices)|full\s+volume|全部(?:数据|重建|切片)|重建全部',clean,re.I):t['sop']['explicit_rows']=False
        if t.get('metadata') and not t['sop'].get('explicit_rows'):t['settings'].update(start_row=0,end_row=t['metadata']['rows'])
        modes=set()
        for match in re.finditer(r'\b(?:manual|traditional|auto(?:matic(?:ally)?)?|sam3)\b|传统|手动|动手|自己(?:选|挑)|自动',clean,re.I):
            if re.search(r"(?:not|no|don.t|do not|不要|不用)\s*$",clean[max(0,match.start()-12):match.start()],re.I):continue
            modes.add('manual' if re.match(r'manual|traditional|传统|手动|动手|自己',match[0],re.I) else 'auto')
        if len(modes)>1:raise ValueError('Please choose manual trials or automatic center search for this step')
        if modes:t['sop']['mode']=modes.pop()
        if re.search(r'\b(?:trials?|candidates?|sweep)\b|候选|抖动|试重建',clean,re.I):
            t['sop']['force_trials']=True
            if not t['sop'].get('mode'):t['sop']['mode']='manual'
        m=re.search(r'(?:text\s*prompt|prompt|feature|target|识别目标|目标)\s*(?:to|is|=|:|为|是|：)?\s*["\']?([A-Za-z][A-Za-z -]{0,40})',clean,re.I)
        if m:
            target=re.split(r'[,.;，。]|\s+(?:and|using|on|with|then|confidence|gpu|range|binning|center)\b',m[1],maxsplit=1,flags=re.I)[0].strip()
            if target.lower() not in ('instance','text'):
                t['settings'].update(prompt=target,prompt_mode='text');t['sop']['target_confirmed']=True
        if re.search(r'(?:angle.*(?:trial|candidate|sweep)|(?:try|trial).*angle|(?:find|search for|optimi[sz]e).*?(?:lamino(?:graphy)? |tilt )?angle)|角度.*(?:候选|试|抖动)|(?:试|抖动|寻找|查找|找).*?(?:倾斜角|lamino angle|角度)',clean,re.I):
            if t['sop'].get('trial_kind')!='angle':t['settings'].update(trial_width=2.,trial_step=.25)
            t['sop'].update(trial_kind='angle',mode='manual',force_trials=True,geometry_confirmed=True);t['settings']['geometry']='laminography'
        for key,pattern in [('dezinger',r'\bdezinger\s*[:=]?\s*(\d+)'),('bright_ratio',r'\bbright[- ]ratio\s*[:=]?\s*(\d+(?:\.\d+)?)')]:
            match=re.search(pattern,clean,re.I)
            if match:t['settings'][key]=int(match[1]) if key=='dezinger' else float(match[1]);changes[key]=t['settings'][key]
        if re.search(r'no stripes?|stripes?\s*(?:off|none)|不去条纹',clean,re.I):t['settings']['remove_stripe_method']='none';changes['remove_stripe_method']='none'
        elif re.search(r'vo[- ]all',clean,re.I):t['settings']['remove_stripe_method']='vo-all';changes['remove_stripe_method']='vo-all'
        if t['settings'].get('bright_ratio',1)<=0:raise ValueError('Bright ratio must be positive')
        paths=input_paths(text)
        if re.search(r'instance|实例|示例',clean,re.I):
            t['sop']['pending_example_paths']=[p for p in paths if Path(p).suffix.lower() in ('.png','.jpg','.jpeg','.tif','.tiff','.bmp')]
        for p in paths:
            if Path(p).suffix.lower() not in ('.h5','.hdf5','.hdf','.png','.tif','.tiff','.jpg','.jpeg','.pt','.pth') and re.search(r'output|save|输出|保存',clean,re.I):t['settings']['output_root']=p;changes['output_root']=p
        if re.search(r'range|范围|step|步长',clean,re.I):t['sop']['pending_range']=clean
        for p in paths:
            if Path(p).suffix.lower() in ('.pt','.pth') and re.search(r'checkpoint|权重',clean,re.I):t['settings']['checkpoint']=p;changes['checkpoint']=p
        return changes
    def _source(self,t,path,text,remote):
        if t.get('state') in ('running','stopping'):
            self.tell(t,'A task is running. Stop it safely or create a new task before replacing its input.','当前任务正在运行。请先安全停止，或新建任务再选择其他输入。');return
        # Reset all source-dependent decisions, including inherited centers and instance references.
        kept={k:t['settings'][k] for k in ('gpu','output_root')}
        t['settings']={**copy.deepcopy(DEFAULTS),**kept};choose_kind(t,'reconstruct');t['metadata']={};t['done']=[];t['center_mode']=None
        t['sop']=dict(enabled=True,phase='reading',geometry_confirmed=False,angle_confirmed=False,mode=None,source=path,candidates=[],timings=[],remote=remote)
        t['cancel_requested']=False
        t['settings']['input_hdf5']=path
        try:self._parameters(t,text)
        except ValueError as e:self.phase(t,'path');self.tell(t,str(e));return
        self.tell(t,'Reading HDF5 information…','正在读取 HDF5 文件信息……')
        def read():
            try:
                before=Path(path).stat();result=inspect_source('input_hdf5',path);after=Path(path).stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('The file changed while reading metadata; retry when acquisition has finished')
                return result
            except Exception as e:return {'error':str(e)}
        def done(meta):
            if t.get('_deleted') or t['settings']['input_hdf5']!=path:return
            if t.get('cancel_requested'):
                t['cancel_requested']=True;self.phase(t,'paused');self.tell(t,'Request cancelled before execution. No reconstruction started.','请求已取消，尚未启动重建。');return
            if 'error' in meta:
                self.phase(t,'path');self.tell(t,'Cannot read this HDF5: '+meta['error']+'\nPlease check the exact path and file format. No reconstruction was started.','无法读取此 HDF5：'+meta['error']+'\n请检查路径和文件格式，尚未启动重建。');return
            t['metadata']=meta
            mark(t,'input_hdf5','rows');n=meta['rows'];s=t['settings']
            if not t['sop'].get('explicit_rows'):s.update(start_row=0,end_row=n)
            t['sop']['source_stat']=[Path(path).stat().st_size,Path(path).stat().st_mtime_ns]
            t['title']='Reconstruct · '+Path(path).stem
            summary=(f"HDF5: {path}\nProjections: {meta['projections']} · Detector: {n} × {meta['width']}\n"
                     f"Pixels: {meta.get('dtype','not recorded')} · Size: {meta.get('size_bytes',0)/1e9:.2f} GB\n"
                     f"Theta: {meta.get('theta_min','?')}–{meta.get('theta_max','?')} {meta.get('theta_unit','')}\n"
                     f"Flat/dark frames: {meta.get('white_shape','?')} / {meta.get('dark_shape','?')}")
            self.tell(t,summary);self.next(t)
        self.w.background(read,done,t['id'])
    def next(self,t):
        p=t['sop'];s=t['settings']
        if p.get('pending_range') and t['metadata']:
            try:self._trial_range(t,p.pop('pending_range'))
            except ValueError as error:self.reject(t,error);return
        if not t['metadata']:self.phase(t,'path');return
        if not p['geometry_confirmed']:
            self.phase(t,'geometry');self.tell(t,'Is this tomography (tomo) or laminography (lamino)? They require different reconstruction geometry. Theta records rotation angles and can exist in both, so it cannot decide this. If unsure, check the acquisition record; I will not guess.','这是 tomography（tomo，常规断层）还是 laminography（lamino，倾斜层析）？两者使用不同的重建几何。theta 只是旋转角度，两类数据都可能包含它，不能据此判断。不确定时请核对采集记录，我不会替你猜。');return
        if s['geometry']=='laminography' and not p['angle_confirmed']:
            self.phase(t,'angle');self.tell(t,'What was the laminography tilt angle, in degrees? Please use the acquisition value; rotation theta is not this tilt.','采集时的 lamino 倾斜角是多少度？请提供采集记录中的值，它与 theta 旋转角不同。');return
        if not p['mode']:
            self.phase(t,'mode');self.tell(t,'Would you like traditional reconstruction (I generate trial images and you choose the center), or automatic center search (SAM3 scores a feature using a text or painted example prompt)? You may also supply a center you already know.','你想用传统重建（生成候选图，由你挑选旋转中心），还是自动找中心（SAM3 用文字或涂画的实例特征评分）？如果已经知道中心，也可以直接给我数值。');return
        if p['mode']=='manual':
            if s.get('segment_all') and p.get('center_valid') and not p.get('target_confirmed'):
                self.phase(t,'target');self.tell(t,'What feature should SAM3 segment after reconstruction? Enter a text prompt or choose an instance example.','重建完成后要分割什么特征？请输入文字目标，或选择一个 instance 示例。');return
            if p.get('trial_kind')=='angle' and s['center']<=0:
                self.phase(t,'trial_center');self.tell(t,'Angle trials need a fixed rotation center. What center should I use?','角度试重建需要固定旋转中心，请提供要使用的中心值。');return
            if p.get('trial_kind')=='angle' and p.get('force_trials'):
                self.phase(t,'trial_offer');self.tell(t,f"Generate angle trials: {s['lamino_angle']:g} ± {s['trial_width']:g} degrees, step {s['trial_step']:g}, fixed center {s['center']:g}. Say generate candidates.",f"将生成角度候选：{s['lamino_angle']:g} ± {s['trial_width']:g} 度，步长 {s['trial_step']:g}，固定中心 {s['center']:g}。回复生成候选。");return
            if s['center']>0 and p.get('center_valid') and not p.get('force_trials'):self.review(t);return
            self.phase(t,'trial_offer');anchor=s['center'] or (t['metadata']['width']-1)/2
            self.tell(t,f'I can generate center candidates around {anchor:g} ± {s["trial_width"]:g} px, step {s["trial_step"]:g}, on the middle detector row. This is a starting range, not a measured center. Say “generate candidates”, or specify a range and step.','我可以先在中间层生成候选图：以 '+f'{anchor:g} ± {s["trial_width"]:g} 像素、步长 {s["trial_step"]:g}。这只是初始搜索范围，不代表真实中心。回复“生成候选”，也可以先指定范围和步长。');return
        if not p.get('target_confirmed'):
            if p.get('pending_example_paths'):
                paths=p.pop('pending_example_paths');self._instance(t,paths,p.get('remote',False));return
            self.phase(t,'target');self.tell(t,'What feature should SAM3 look for? Enter a text prompt such as particle, or say “instance” and provide an example image to paint.','SAM3 要找什么特征？可以直接输入文字目标，例如 particle（颗粒）；也可以说“instance”，提供示例图片并涂画一个特征。');return
        if p.get('full_requested') and not p.get('center_only'):
            self.review(t,automatic=not p.get('center_valid',False));return
        self.phase(t,'search_offer');target='painted instance' if s['prompt_mode']=='instance' else s['prompt']
        self.tell(t,f'Automatic center search will use {s["geometry"]}, target {target}, GPU {s["gpu"]}. It will only find a center; full reconstruction requires a separate confirmation. Say “start center search”.',f'将使用 {s["geometry"]}、目标 {target}、GPU {s["gpu"]} 自动找中心。此步只找中心，不会重建全部数据。回复“开始找中心”。')
    def review(self,t,automatic=False):
        s=t['settings'];meta=t['metadata'];factor=2**s['binning'];count=(s['end_row']-s['start_row'])//factor
        if not automatic and (not t['sop'].get('center_valid') or not 0<s['center']<meta['width']):self.phase(t,'parameters');self.tell(t,'Please select a center inside the detector width.','请选择探测器宽度范围内的旋转中心。');return
        if not 0<=s['start_row']<s['end_row']<=meta['rows'] or count<1:self.phase(t,'parameters');self.tell(t,'The requested row range is invalid for this input and binning. Please give a valid start/end row.','层范围超出当前数据，或小于 binning 因子，请重新提供起止层。');return
        if s['geometry']=='laminography' and s['method'] not in ('fourierrec','linerec'):self.phase(t,'parameters');self.tell(t,'Laminography uses FourierRec or LineRec. Which would you like?','Lamino 仅支持 FourierRec 或 LineRec，请选择其中一个。');return
        self.phase(t,'confirm');t['sop']['automatic_full']=automatic;t['sop']['review_fingerprint']=fingerprint(t);t['state']='draft';choose_kind(t,'analyze' if automatic else 'reconstruct');t['center_mode']='auto' if automatic else 'known';mark(t,'rows','input_hdf5')
        from .protocol import validate_settings
        validate_settings(s)
        if s['geometry']=='laminography' and s['lamino_angle']==0:self.tell(t,'Please provide the signed nonzero lamino angle.','请输入带正负号的非零 lamino 倾角。');return
        angle=f" · tilt {s['lamino_angle']:g}°" if s['geometry']=='laminography' else ''
        center_text='automatic SAM3 search ('+('instance' if s['prompt_mode']=='instance' else s['prompt'])+')' if automatic else f"{s['center']:g} px"
        details=(f"{s['input_hdf5']}\n{s['geometry']}{angle} · {s['method']}\nCenter: {center_text} · GPU {s['gpu']}\n"
                 f"Rows [{s['start_row']}, {s['end_row']}) · Binning {factor}×{factor} · {count} images, {meta['width']//factor}×{meta['width']//factor}\n"
                 f"Output: a NEW task folder under {s['output_root']}\nPreprocessing: stripes {s.get('remove_stripe_method','vo-all')}, dezinger {s.get('dezinger',0)}, bright ratio {s.get('bright_ratio',1):g}\nTIFF pixel data: approximately {count*(meta['width']//factor)**2*4/1e9:.2f} GB\n{estimate(t)}")
        if s.get('segment_all'):
            details+='\nSegment All: yes. Segmentation time is additional and has not been measured.'
        if automatic:
            target='instance example' if s['prompt_mode']=='instance' else s['prompt']
            bounds='global' if s['range_low'] is None else f"{s['range_low']:g}–{s['range_high']:g}"
            details+=f"\nSAM3 target: {target} · center search: {bounds}, final step {s['target_step']:g} px. Search time is additional and has not yet been measured."
        self.tell(t,'Before full reconstruction, please check:\n'+details+'\nReply “confirm reconstruction” to run, change parameters, or cancel. Nothing starts from this preview.','全量重建前，请核对：\n'+details+'\n回复“确认重建”才会执行；也可以改参数或取消。显示这份清单不会启动重建。');self.w.save(t)
    def launch(self,t,stage):
        s=t['settings'];p=t['sop'];p['active_stage']=stage;p['phase']='dispatch';t['state']='draft';t['run_requested']=False
        if stage=='angle_trial':choose_kind(t,'try_angle');t['center_mode']='known'
        elif stage=='trial':p['center_valid']=False;choose_kind(t,'try_center');t['center_mode']='known'
        elif stage=='auto_full':choose_kind(t,'analyze');t['center_mode']='auto';t['prompt_confirmed']=True;mark(t,'prompt')
        elif stage=='search':choose_kind(t,'find_center');t['search_mode']='auto';t['prompt_confirmed']=True;mark(t,'prompt')
        else:choose_kind(t,'reconstruct');t['center_mode']='known'
        if stage=='pilot':
            p['full_rows']=[s['start_row'],s['end_row']];factor=2**s['binning'];middle=t['metadata']['rows']//2;start=min(max(0,middle//factor*factor),t['metadata']['rows']-factor*4);start=max(0,start);s.update(start_row=start,end_row=min(t['metadata']['rows'],start+factor*4));mark(t,'rows')
        mark(t,'input_hdf5','rows');self.w.add(t,'assistant','');t['reply_id']=t['messages'][-1]['id'];self.w.start_task(t)
        if t['state']=='running':p['phase']='running'
        else:p['phase']='interrupted'
        self.w.save(t)
    def reject(self,t,error):
        if self.enabled(t) and t['state'] not in ('running','stopping'):
            t['sop'].pop('review_fingerprint',None)
            self.phase(t,'edit_error' if t.get('metadata') else 'path')
        self.tell(t,str(error))

    def restore(self,t):
        p=t.get('sop',{})
        if not p.get('enabled'):return
        if p.get('phase')=='dispatch' and t['state'] in ('running','stopping'):
            p['phase']='running';return
        if p.get('phase') in ('reading','dispatch') or p.get('phase')=='running' and t['state'] not in ('running','stopping'):
            if p.get('active_stage')=='pilot' and p.get('full_rows'):t['settings']['start_row'],t['settings']['end_row']=p.pop('full_rows')
            p['phase']='interrupted';t['run_requested']=False;t['awaiting_confirmation']=False

    def _check_source(self,t):
        path=Path(t['settings']['input_hdf5']);stat=path.stat()
        if t['sop'].get('source_stat')!=[stat.st_size,stat.st_mtime_ns]:
            raise ValueError('The input changed. Paste its path again to reload metadata before starting.')
        s=t['settings'];meta=t['metadata']
        if not 0<=s['start_row']<s['end_row']<=meta['rows']:raise ValueError('Row range is outside this input')
        if s['geometry']=='laminography' and (not t['sop'].get('angle_confirmed') or s['lamino_angle']==0):raise ValueError('Provide the signed nonzero laminography tilt angle')

    def before_start(self,t):
        if t['kind'] not in KINDS:return True
        if self.enabled(t) and t['sop'].get('phase')=='dispatch':
            self._check_source(t);return True
        if not self.enabled(t):self.bootstrap(t)
        if not t['metadata'] or t['sop'].get('source')!=t['settings']['input_hdf5']:
            self._source(t,t['settings']['input_hdf5'],'',False)
        else:self.next(t)
        return False
    def guard_advance(self,t):
        if t['kind'] not in KINDS:return False
        if not self.enabled(t):
            self.bootstrap(t)
            if t['settings']['input_hdf5']:self._source(t,t['settings']['input_hdf5'],'',False)
            else:self.tell(t,'Please paste the HDF5 path first.','请先粘贴 HDF5 路径。')
        elif t['sop']['phase'] not in ('running','reading','confirm','choose','choose_angle','search_offer','trial_offer','target','instance','interrupted','paused'):
            self.next(t)
        return True
    def _instance(self,t,paths,remote):
        if remote and len(paths)<2:
            self.tell(t,'Painting an instance needs the desktop window. On your phone you can provide two exact local paths: the example image and its binary mask, or choose a text prompt.','涂画实例需要在电脑窗口完成。手机端可以提供示例图和二值 mask 的两个本地路径，或改用 text prompt。');return
        sys.path.insert(0,str(RECON))
        from sam3_rotation_center.exemplar import read_reference,InstanceExample,save_example
        from PIL import Image
        import numpy as np
        try:
            if len(paths)>=2:
                image=read_reference(paths[0])
                with Image.open(paths[1]) as m:mask=np.asarray(m.convert('L'))>0
                example=InstanceExample(image,mask,paths[0]).validate()
            else:
                from PySide6.QtWidgets import QFileDialog,QDialog
                from ct_recon_gui.instance_dialog import InstanceDialog
                source=paths[0] if paths else QFileDialog.getOpenFileName(self.w,'Example image','','Images (*.png *.tif *.tiff *.jpg *.jpeg *.bmp)')[0]
                if not source:self.phase(t,'target');return
                dialog=InstanceDialog(read_reference(source),source,self.w)
                if dialog.exec()!=QDialog.Accepted:self.phase(t,'target');return
                example=dialog.example
            reference=save_example(example,STATE_ROOT/'instance_examples'/uuid.uuid4().hex)
            t['settings'].update(prompt_mode='instance',prompt='visual',instance_reference=reference);t['sop']['target_confirmed']=True;self.next(t)
        except Exception as e:self.tell(t,'Could not use that instance: '+str(e),'无法使用这个实例：'+str(e))
    def handoff(self,t,text,remote):
        from .chat_flow import execution_intent
        clean=clean_text(text)
        if not execution_intent(clean):return False
        segment=bool(re.search(r'\bsegment\b|分割',clean,re.I))
        training=bool(re.search(r'\btrain\b|fine[- ]?tune|训练|微调',clean,re.I))
        if not (segment or training):return False
        target=self.w.repo.create();target['language']=t.get('language','en')
        self.w.tasks={target['id']:target,**self.w.tasks};choose_kind(target,'segment' if segment else 'train')
        target['settings']['output_root']=t['settings']['output_root'];target['settings']['gpu']=t['settings']['gpu']
        paths=input_paths(text)
        field='image_folder' if segment else 'dataset'
        inputs=[p for p in paths if Path(p).suffix.lower() not in ('.pt','.pth')]
        if inputs:target['settings'][field]=inputs[0]
        elif segment and re.search(r'results?|these|those|刚才|这些|结果',clean,re.I):
            from .results import result_context
            for record in reversed(result_context(t)):
                if record.get('state')=='succeeded' and record['action'] in ('reconstruct','analyze'):
                    folder=Path(record['output'])/'reconstruction'
                    if folder.is_dir():target['settings']['image_folder']=str(folder);break
        self.w.add(target,'user',text);self.w.save(target)
        self.tell(t,'Created a separate '+('segmentation' if segment else 'training')+' task. Your reconstruction history is preserved.','已新建'+('分割' if segment else '训练')+'任务，重建记录保留在当前任务里。')
        if remote:self.w.telegram.subscribe(target,False)
        else:self.w.select_task(target['id'])
        if target['settings'].get(field):
            self.w.add(target,'assistant','');target['reply_id']=target['messages'][-1]['id'];self.w.inspect(target,field,target['settings'][field])
        else:self.w.guide(target)
        self.w.refresh_list()
        return True

    def handle(self,t,text,remote=False):
        clean=clean_text(text).strip();low=clean.lower().strip(' .!。！');paths=input_paths(text);h5=[p for p in paths if Path(p).suffix.lower() in ('.h5','.hdf5','.hdf')]
        recon_words=bool(re.search(r'\brecon(?:struct(?:ion)?)?\b|重建|旋转中心|rotation center|center (?:search|trials?)',clean,re.I))
        if not self.enabled(t) and not paths and re.search(r'^(?:what|why|how|explain|什么是|解释)',low):return False
        if re.search(r'flat(?:[- ]file)?|平场',clean,re.I) and len(h5)>1:
            self.tell(t,'This workflow currently uses the selected input’s flat/dark frames. A separate flat-file argument is not supported here yet; please use a calibrated input HDF5 or the reconstruction command line.','当前流程使用输入 HDF5 内的平场/暗场，暂不支持单独指定外部平场文件。请使用已配好校正数据的 HDF5，或重建命令行。');return True
        folder_input=len(paths)==1 and (t['kind'] is None or t['kind'] in KINDS) and Path(paths[0]).is_dir() and any(x.suffix.lower() in ('.h5','.hdf5','.hdf') for x in Path(paths[0]).iterdir() if x.is_file())
        if not self.enabled(t) and not (folder_input or h5 and (t['kind'] in KINDS or t['kind'] is None or recon_words) or recon_words and t['kind'] in (None,*KINDS)):return False
        from .request_limits import unsupported_request,MESSAGES
        unsupported=unsupported_request(text)
        if unsupported:
            self.tell(t,*MESSAGES[unsupported]);return True
        self.bootstrap(t);p=t['sop'];p['remote']=remote
        if p['phase'] in ('complete','center_ready') and not recon_words and self.handoff(t,text,remote):return True
        changed=False
        if len(h5)==1 and Path(h5[0]).is_file():
            stat=Path(h5[0]).stat();changed=p.get('source_stat')!=[stat.st_size,stat.st_mtime_ns]
        if h5 and (changed or len(h5)>1 or p['phase']=='path' or path_key(h5[0])!=path_key(p.get('source',''))):
            if len(h5)>1:
                p['files']=h5;p['file_request']=text;self.phase(t,'file');self.tell(t,'Please choose one HDF5 for this task:\n'+'\n'.join(f'{i}. {x}' for i,x in enumerate(h5,1)),'本次先选择一份 HDF5：\n'+'\n'.join(f'{i}. {x}' for i,x in enumerate(h5,1)));return True
            self._source(t,h5[0],text,remote);return True
        if p['phase']=='file':
            if low.isdigit() and 1<=int(low)<=len(p['files']):self._source(t,p['files'][int(low)-1],p.get('file_request','')+'\n'+text,remote)
            else:self.tell(t,'Please give the file number or exact path.','请提供文件编号或完整路径。')
            return True
        if p['phase']=='path':
            if paths and Path(paths[0]).is_dir():
                files=sorted(str(x) for x in Path(paths[0]).iterdir() if x.is_file() and x.suffix.lower() in ('.h5','.hdf5','.hdf'))
                if len(files)==1:self._source(t,files[0],text,remote)
                elif files:p['files']=files;p['file_request']=text;self.phase(t,'file');self.tell(t,'Choose one HDF5:\n'+'\n'.join(f'{i}. {x}' for i,x in enumerate(files,1)),'请选择一份 HDF5：\n'+'\n'.join(f'{i}. {x}' for i,x in enumerate(files,1)))
                else:self.tell(t,'No HDF5 files in that folder. Please paste an exact file path.','该文件夹没有 HDF5，请粘贴文件完整路径。')
            else:self.tell(t,'Please paste the exact HDF5 file path.','请先粘贴 HDF5 文件的完整路径。')
            return True
        if t['state'] in ('running','stopping'):
            if low in ('cancel','pause','取消','暂停'):
                self.w.stop_task(t);return True
            if re.search(r'what|why|how|为什么|是什么',low):return False
            self.tell(t,'This task is running. Ask for progress, or stop it safely before changing parameters.','任务正在运行。可以询问进度，或先安全停止再修改参数。');return True
        if low in ('cancel','pause','取消','先不做','暂停','no','nope','不要','取消重建'):
            t['cancel_requested']=True;self.phase(t,'paused');self.tell(t,'Paused. No further reconstruction will start. Say “continue” when ready.','已暂停，不会继续启动重建。准备好后可回复“继续”。');return True
        if p['phase']=='reading':
            self.tell(t,'Still reading metadata; no reconstruction has started. You can cancel this request.','仍在读取文件信息，尚未开始重建；可以取消本次请求。');return True
        if p['phase']=='center_ready':
            if re.search(r'recon|continue|重建|继续',low):
                self._parameters(t,text);p.update(full_requested=True,center_only=False);self.review(t)
            else:self.tell(t,f"Saved center: {t['settings']['center']:g} px. Say reconstruct all to review a full run, or ask to see the results.",f"中心已保存：{t['settings']['center']:g} 像素。需要全量重建时告诉我，我会先列出参数供你确认。")
            return True
        if p['phase'] in ('paused','interrupted'):
            if low in ('continue','retry','resume','继续','重试'):
                if not t['metadata']:
                    self._source(t,t['settings']['input_hdf5'],'',remote);return True
                if p.get('active_stage') in ('trial','angle_trial'):p['force_trials']=True;p['mode']='manual'
                elif p.get('active_stage')=='search':p['mode']='auto';p['full_requested']=False
                if p.get('center_valid') and t['settings']['center']>0:self.review(t)
                else:self.next(t)
            else:self.tell(t,'Say “continue” to review the workflow, or paste a new input path.','回复“继续”重新核对流程，或粘贴新的输入路径。')
            return True
        if p['phase'] in ('choose','choose_angle'):
            if re.search(r'(?:open|show|打开|看看).*(?:folder|result|文件夹|结果)',low):
                opened=self.open_folder(t,p['candidate_folder']);self.tell(t,('Opened: ' if opened else 'Folder: ')+p['candidate_folder']);return True
            if re.search(r'generate|again|range|step|重新|再生成|扩大|范围|步长',low):p['force_trials']=True;p['mode']='manual';self._trial_range(t,clean);self.next(t);return True
            is_angle=p['phase']=='choose_angle';center,error=selection(text,p['candidates'],t['metadata']['width'],'angle' if is_angle else 'center')
            if error:self.tell(t,error,'尚无法确定你选的是哪张。请给出中心数值、“第3张”这样的编号，或完整文件名。\n'+error)
            else:
                t['settings']['lamino_angle' if is_angle else 'center']=center;p['center_valid']=True
                if is_angle:p['angle_confirmed']=True
                p['selection']=dict(value=center,quantity='angle' if is_angle else 'center',user_text=text);p['force_trials']=False;self.review(t)
            return True
        if p['phase'] not in ('path','file','reading','geometry','angle') and (re.search(r'instance|实例|例子|示例|涂画',low) or any(Path(x).suffix.lower() in ('.png','.jpg','.jpeg','.tif','.tiff','.bmp') for x in paths)):
            if p.get('mode')!='manual' or not t['settings'].get('segment_all'):p['mode']='auto'
            p['target_confirmed']=False;self.phase(t,'instance');self._instance(t,paths,remote);return True
        if p['phase']=='trial_center' and re.fullmatch(r'\d+(?:\.\d+)?',low):
            center=float(low)
            if not 0<center<t['metadata']['width']:self.tell(t,'Center outside the detector width.','中心超出探测器范围。');return True
            t['settings']['center']=center;p['center_valid']=True;self.next(t);return True
        if p['phase']=='angle' and re.fullmatch(r'-?\d+(?:\.\d+)?\s*(?:degrees?|度|°)?',low):
            angle=float(re.search(r'-?\d+(?:\.\d+)?',low)[0])
            if not -89.9<=angle<=89.9 or angle==0:self.tell(t,'Please enter an angle between -89.9 and 89.9 degrees.','请输入 -89.9 到 89.9 度之间的倾角。');return True
            t['settings']['lamino_angle']=angle;p['angle_confirmed']=True;self.next(t);return True
        if p['phase']=='target' and re.search(r'^(?:cancel|no|not |don.t|不要|取消|先不)',low):
            self.tell(t,'Please name the feature you want to find, or cancel the workflow.','请输入要识别的特征名称，或者取消本次流程。');return True
        if p['phase'] in ('target','instance') and not re.search(r'\b(?:what|why|how|explain)\b|什么|为什么|怎么',low):
            target=re.sub(r'^(?:text\s*prompt|prompt|text|文字|目标)\s*[:：=]?\s*','',clean,flags=re.I).strip('"\' ')
            if target and len(target)<=80:
                target={'颗粒':'particle','粒子':'particle','孔':'pore','孔隙':'pore'}.get(target,target)
                t['settings'].update(prompt_mode='text',prompt=target,instance_reference={});p['target_confirmed']=True;self.next(t);return True
        if p['phase']=='edit_error' and confirmation(low):
            self.next(t);return True
        if p['phase']=='confirm' and confirmation(low):
            try:valid=p.get('review_fingerprint')==fingerprint(t)
            except OSError:valid=False
            source=Path(t['settings']['input_hdf5'])
            if source.exists() and p.get('source_stat')!=[source.stat().st_size,source.stat().st_mtime_ns]:
                self._source(t,str(source),'',remote);return True
            if not valid:self.tell(t,'The input or settings changed. Please review the updated plan first.','输入文件或设置发生变化，请先重新核对计划。');self.review(t,automatic=p.get('automatic_full',False))
            else:self.launch(t,'auto_full' if p.get('automatic_full') else 'full')
            return True
        if p['phase']=='confirm' and low in ('measure time','pilot','先测时','先测一下','测时'):
            self.tell(t,'I will measure a few middle slices using the selected center and geometry. Full reconstruction will still need confirmation.','先用选定的中心和几何重建几层测时；测完仍需确认才会全量重建。')
            if not p.get('center_valid'):
                p['pilot_after_search']=True;self.launch(t,'search')
            else:self.launch(t,'pilot')
            return True
        if p['phase']=='trial_offer' and (confirmation(low) or re.fullmatch(r'(?:generate|start)(?: (?:the )?(?:candidates|trials|sweep))?|生成候选|开始生成|生成候选图',low)):self._trial_range(t,clean);self.launch(t,'angle_trial' if p.get('trial_kind')=='angle' else 'trial');return True
        if p['phase']=='search_offer' and (confirmation(low) or re.search(r'^(?:start|run|find|开始|找中心|确认)',low)):self.launch(t,'search');return True
        if p['phase']=='center_ready' and low in ('result correct','looks correct','结果正确','结果是对的'):
            self.tell(t,'Saved your review. Tell me when you want to reconstruct.','已记录你确认结果正确。需要重建时告诉我即可。');return True
        if p['phase']=='complete' and low in ('repeat','again','重新重建','再重建一次'):self.review(t);return True
        if re.search(r'^(?:what|why|how|explain)\b|为什么|是什么|不懂|不知道|不清楚',low):
            if p['phase']=='geometry':self.next(t);return True
            return False
        old_geometry=t['settings']['geometry']
        try:changes=self._parameters(t,text)
        except ValueError as e:self.reject(t,e);return True
        if changes.get('geometry') and changes['geometry']!=old_geometry:
            t['settings']['center']=changes.get('center',0);p['center_valid']='center' in changes;p['force_trials']=False
            if changes['geometry']=='laminography' and 'lamino_angle' not in changes:p['angle_confirmed']=False
            self.next(t);return True
        if p['phase']=='confirm':self.next(t);return True
        if p['phase']=='trial_offer':self._trial_range(t,clean)
        self.next(t);return True
    def _trial_range(self,t,text):
        s=t['settings'];m=re.search(r'(?:range|范围)\s*[:：=]?\s*(-?\d+(?:\.\d+)?)\s*(?:to|[-–]|到|至)\s*(-?\d+(?:\.\d+)?)',text,re.I)
        if m:
            lo,hi=map(float,m.groups())
            if (t['sop'].get('trial_kind')=='angle' and not -89.9<lo<hi<89.9) or (t['sop'].get('trial_kind')!='angle' and not 0<lo<hi<t['metadata']['width']):raise ValueError('Trial range must lie inside the detector width')
            if t['sop'].get('mode')=='auto':s.update(range_low=lo,range_high=hi)
            else:
                s.update(trial_width=(hi-lo)/2)
                if t['sop'].get('trial_kind')=='angle':s['lamino_angle']=(lo+hi)/2
                else:s['center']=(lo+hi)/2;t['sop']['center_valid']=False
        m=re.search(r'(?:step|步长)\s*[:：=]?\s*(\d+(?:\.\d+)?)',text,re.I)
        if m:
            step=float(m[1])
            if step<=0:raise ValueError('Step must be greater than zero')
            s['initial_step' if t['sop'].get('mode')=='auto' else 'trial_step']=step
        if t['sop'].get('mode')=='auto':return
        if 2*s['trial_width']/s['trial_step']>500:raise ValueError('This would generate more than 500 candidates. Increase the step or narrow the range first.')
    def completed(self,t,job,status):
        stage=job.get('sop_stage')
        if not stage or not self.enabled(t):return False
        p=t['sop'];s=t['settings'];entry=next((x for x in t['messages'] if x['id']==job.get('reply_id')),None)
        if entry:
            from .chat_flow import finish_activity
            finish_activity(t,entry['id']);entry['text']=say(t,'Stage completed.','当前步骤已完成。') if status['state']=='succeeded' else status.get('error','Stopped')
        if status['state']!='succeeded':
            if stage=='pilot' and p.get('full_rows'):s['start_row'],s['end_row']=p.pop('full_rows')
            self.phase(t,'interrupted');t['state']='stopped' if status['state'] in ('cancelled','stopped') else 'failed';self.tell(t,'This step did not complete. Partial results were kept. Say “retry” to review a fresh attempt; full reconstruction has not been authorized by this failure.','此步未完成，部分结果已保留。回复“重试”可重新核对；失败不会自动触发全量重建。');return True
        result=status.get('result',{});t['state']='draft'
        if stage in ('trial','angle_trial'):
            items=result.get('candidate_catalogue') or catalogue(result.get('files',[]))
            if not items:self.phase(t,'interrupted');self.tell(t,'No usable candidates were saved.','没有可用的候选结果。');return True
            meta=read_json(Path(result['folder'])/'run_metadata.json')
            actual=meta.get('method','').removeprefix('lamino_')
            if actual==s['method'] and meta.get('elapsed_seconds'):
                sample={k:s[k] for k in ('input_hdf5','geometry','lamino_angle','method','binning','gpu')};sample.update(key=timing_key(t),seconds=meta['elapsed_seconds'],slices=len(items));p.setdefault('timings',[]).append(sample);self.remember_timing(sample)
            p['candidates']=items;p['candidate_folder']=result.get('preview_folder') or result['folder'];self.phase(t,'choose_angle' if stage=='angle_trial' else 'choose')
            opened=self.open_folder(t,p['candidate_folder']);unit='°' if stage=='angle_trial' else 'px';quantity='angle' if stage=='angle_trial' else 'center'
            mapping='\n'.join(f"{i['index']}: {i['value']:g} {unit}" for i in items[:30])
            self.tell(t,f"Saved {len(items)} candidates. {'Opened' if opened else 'Folder'}: {p['candidate_folder']}\n{mapping}\nWhich {quantity} looks best? Give a {quantity} value, “candidate 3”, or a filename. The numbered PNGs and CSV use this exact order.",f"已保存 {len(items)} 张候选图。{'已打开文件夹' if opened else '文件夹'}：{p['candidate_folder']}\n{mapping}\n你选哪张？可以回复参数数值、“第3张”或文件名。编号 PNG 和 CSV 使用同一顺序。")
        elif stage=='search':
            center=result.get('recommended_center')
            if center is None:self.phase(t,'interrupted');self.tell(t,'No center was saved by the search.','自动搜索未保存有效中心。');return True
            s['center']=float(center);p['center_valid']=True;p['force_trials']=False
            self.tell(t,f'Center search completed: {center:g} px. No full reconstruction has started.',f'自动找中心完成：{center:g} 像素。尚未开始全量重建。')
            if p.pop('pilot_after_search',False):self.launch(t,'pilot')
            elif p.get('full_requested') and not p.get('center_only'):self.review(t)
            else:self.phase(t,'center_ready');t['state']='completed'
        else:
            folder=Path(job['job_dir'])/'results/reconstruction';metadata=read_json(folder/'run_metadata.json');sample={k:s[k] for k in ('input_hdf5','geometry','lamino_angle','method','binning','gpu')};sample.update(key=timing_key(t),seconds=metadata.get('elapsed_seconds',status.get('elapsed_seconds',0)),slices=result.get('slices',result.get('reconstructed_slices',1)));p.setdefault('timings',[]).append(sample);self.remember_timing(sample)
            if stage=='pilot':
                s['start_row'],s['end_row']=p.pop('full_rows');self.tell(t,f"Timing sample saved: {result.get('slices',0)} slices.",f"测时完成：{result.get('slices',0)} 层。");self.review(t)
            else:
                if stage=='auto_full':p['center_valid']=True;s['center']=float(result.get('center_search',{}).get('recommended_center',s['center']))
                self.phase(t,'complete');t['state']='completed';self.tell(t,'Full reconstruction completed. Results: '+result.get('folder',status.get('output','')),'全量重建完成。结果目录：'+result.get('folder',status.get('output','')))
        self.w.save(t);return True
    def remember_timing(self,sample):
        from .jobs import atomic_json
        atomic_json(STATE_ROOT/'reconstruction_timings.json',(read_json(STATE_ROOT/'reconstruction_timings.json',[])+[sample])[-100:])
    def open_folder(self,t,path):
        if t['sop'].get('remote'):return False
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))
