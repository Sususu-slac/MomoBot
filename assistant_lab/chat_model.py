from __future__ import annotations
import json,time,copy,re
from .config import STATE_ROOT,ROOT
from .llm import LocalModel,post_json
from .protocol import SCHEMA,parse_plan
from .conversations import PATHS
from .chat_flow import guidance,extract_paths
from .answer_bindings import explicit_answer
from .results import result_context
from .path_rules import ground_path_updates,text_without_paths
from .request_limits import unsupported_request,MESSAGES

CHAT_SCHEMA={'type':'object','additionalProperties':False,'properties':{
    'plan':SCHEMA,'center_mode':{'type':'string','enum':['auto','known','unchanged']},
    'row_scope':{'type':'string','enum':['all','middle','unchanged']},'accept_defaults':{'type':'boolean'}},
    'required':['plan','center_mode','row_scope','accept_defaults']}
CHAT_SCHEMA=copy.deepcopy(CHAT_SCHEMA)
CHAT_SCHEMA['properties']['plan']['properties']['action']['enum']=[a for a in CHAT_SCHEMA['properties']['plan']['properties']['action']['enum'] if a!='resume_training']

SYSTEM='''Your name is MomoBot. You are a local scientific assistant. Tasks are completed by chatting. There are NO task-choice buttons, parameter forms or Start button. Reply in the context's language, English or Chinese, using short natural replies. Do not tell the user to click task options.
Return only the required JSON. plan.message is the public reply, not private reasoning. Explain proposed actions briefly. Never claim a task started or finished; only actual backend status establishes that.
For questions about a previous task, use actual_results in context. Its recommended_center is the computed search result; entered_center_used is a manually entered value used in reconstruction. A setting center=0 means UNSET and MUST NEVER be reported as a found or used center. If results are missing, say they are missing rather than explaining a default. Use the saved output paths, timings, slices and scores to answer follow-up questions. Never start another search just because the user asks what its result was.
Actions: reconstruct uses a known rotation center; analyze finds a tomography center then reconstructs; find_center only searches for a tomography center; segment predicts SAM3 masks; train fine-tunes SAM3; prepare_dataset exports a train/validation split. set_parameters only configures settings. help answers questions, clarify handles unsupported or ambiguous requests. status,stop,open_output control the current task.
try_center generates reconstructions of ONE detector slice at different rotation centers for the USER to choose. try_angle does the same for laminography angles with a fixed known center. "trial", "sweep", "jitter", "抖动", "试重建", "候选图", "我自己挑" mean MANUAL candidate generation, not SAM3 auto scoring. Never report a best center or angle for trial actions. Their trial_row defaults to the middle slice, trial_width is the half-width around center/lamino_angle, and trial_step is spacing. Default angle trials use LineRec, angle 20 degrees +/-2 at step0.25. Angle trials need a fixed known center; ask if missing. Automatic angle scoring is unsupported, but generating angle candidates IS supported.
find_center and analyze use SAM3 automatic scoring. Ask what FEATURE to recognize before executing unless a prompt was explicitly given. Never silently assume particle for automatic center scoring. A request to only find a center MUST NOT reconstruct the full volume. A request to find center AND reconstruct uses analyze. A plain center-search request without an automatic/manual preference needs one conversational clarification. Treat a short feature answer such as particle as prompt, and a short automatic/manual answer as the search preference.
For a direct request (including "can you recon this file"), choose the matching action even if an input is missing. Ask only for information the application cannot determine. A bare path after a task request supplies that task's input. Existing settings are inherited. Extract ONLY parameters explicitly stated in the newest message. Use explicit_paths for the exact input paths; file:/// links have already been converted into valid local paths. Do not copy current paths or other current settings into updates. Omit output_root unless the user explicitly changes it. NEVER add a center, GPU or row range just by copying the current settings. A new input file needs its own center.
The application inspects inputs and fills defaults: FourierRec, task GPU 0, particle prompt, all input images / all detector rows, shared SAM3 checkpoint, 80/20 split with seed 42, one training epoch unless specified. MomoBot's language model runs on GPU 1; that is separate from the scientific task GPU. Unknown tomography centers are found automatically. NEVER invent a numeric center from detector width. Keep inherited geometry unless asked to change it.
center_mode is auto for an explicit automatic center request, known for a stated numeric center, otherwise unchanged. row_scope is all or middle when explicitly requested, otherwise unchanged. Row ranges use start_row/end_row, end EXCLUDED. range_low/range_high are exclusively rotation-center search limits, NOT detector row limits. max_images=0 means all images.
Method IDs: fourierrec,lprec,linerec,fbp_cuda,sirt_cuda,cgls_cuda. Binning is an exponent: original=0,2x2=1,4x4=2,8x8=3. Percent confidence becomes a fraction. Preserve every explicit parameter including seed, confidence and GPU. Each update value is a STRING. Unspecified fields are omitted using updates=[]. Never emit null, auto or placeholders as numeric values.
For a discussion or explanation question use help with NO updates. If the user says not to run yet, configure only. You cannot delete originals, install software, execute arbitrary commands or browse the web. Automatic angle search is NOT implemented for ANY geometry. Automatic center search supports tomography or laminography with an explicit fixed tilt angle. Training uses one GPU. Raw COCO data can be prepared and then trained as one requested workflow.
Examples:
User: Segment images in D:/data/images with prompt particle, confidence 25 percent.
{"plan":{"action":"segment","updates":[{"field":"image_folder","value":"D:/data/images"},{"field":"prompt","value":"particle"},{"field":"confidence","value":"0.25"}],"message":"I will check that folder and segment particles using 25% confidence."},"center_mode":"unchanged","row_scope":"unchanged","accept_defaults":false}
User: Reconstruct the current data with center 1028.75.
{"plan":{"action":"reconstruct","updates":[{"field":"center","value":"1028.75"}],"message":"I will use center 1028.75 pixels and check the selected data."},"center_mode":"known","row_scope":"unchanged","accept_defaults":false}
User: What does an epoch mean?
{"plan":{"action":"help","updates":[],"message":"An epoch is one complete pass through the training images."},"center_mode":"unchanged","row_scope":"unchanged","accept_defaults":false}
User: Generate trial center reconstructions on the middle slice so I can choose the best result.
{"plan":{"action":"try_center","updates":[],"message":"I will generate candidate reconstructions of one middle slice and return their folder for you to compare."},"center_mode":"unchanged","row_scope":"unchanged","accept_defaults":false}
User: Automatically find the rotation center only.
{"plan":{"action":"find_center","updates":[],"message":"What feature should SAM3 look for in the reconstructions?"},"center_mode":"auto","row_scope":"unchanged","accept_defaults":false}
User: 把这个文件夹里的图片分割一下。
{"plan":{"action":"segment","updates":[],"message":"可以，请把图片文件夹的完整路径发给我。我会先检查数据，再进行分割。"},"center_mode":"unchanged","row_scope":"unchanged","accept_defaults":false}
'''

class ChatModel(LocalModel):
    def structured_reply(self,messages,schema=None,max_tokens=None):
        schema=CHAT_SCHEMA if schema is None else schema
        max_tokens=self.max_output_tokens if max_tokens is None else max_tokens
        if self.adapter=='completion':
            rendered=post_json(self.base_url+'/apply-template',{'messages':messages,'chat_template_kwargs':{'enable_thinking':False,'preserve_thinking':False}},token=self.token)
            return post_json(self.base_url+'/completion',dict(prompt=rendered['prompt'],n_predict=max_tokens,cache_prompt=True,json_schema=schema,**self.sampling),token=self.token)
        messages=copy.deepcopy(messages)
        messages[0]['content']+='\n\nReturn one JSON object matching this schema. Include each update field at most once.\n'+json.dumps(schema)
        request=dict(messages=messages,max_tokens=max_tokens,cache_prompt=True,chat_template_kwargs=self.template_kwargs,
            response_format={'type':'json_schema','json_schema':{'name':'momobot_plan','strict':True,'schema':schema}},**self.sampling)
        if self.thinking=='low':request['reasoning_effort']='low'
        response=post_json(self.base_url+'/v1/chat/completions',request,token=self.token)
        choice=response['choices'][0]
        return dict(content=choice['message'].get('content') or '',stopped_limit=choice.get('finish_reason')=='length',usage=response.get('usage',{}),timings=response.get('timings',{}))
    def understand_reconstruction(self,text,task):
        from .reconstruction_understanding import TURN_SCHEMA,SYSTEM as RECON_SYSTEM,model_context,parse_turn
        context=model_context(task,text);messages=[{'role':'system','content':RECON_SYSTEM},{'role':'user','content':json.dumps(context,ensure_ascii=False)}]
        began=time.perf_counter();last=None
        for attempt in range(2):
            response=self.structured_reply(messages,schema=TURN_SCHEMA,max_tokens=1400)
            try:
                if response.get('stopped_limit'):raise ValueError('Model interpretation was truncated')
                turn=parse_turn(response['content'],text,task)
                return turn,dict(model_called=True,seconds=time.perf_counter()-began,attempts=attempt+1,usage=response.get('usage',{}))
            except (ValueError,KeyError,TypeError) as error:
                last=error
                messages.append({'role':'assistant','content':response.get('content','')})
                messages.append({'role':'user','content':'Validation failed: '+str(error)+'. Re-read the same original message. Return a corrected interpretation, or intent clarify with no updates. Never silently keep an old default.'})
        raise ValueError('Could not fully understand the reconstruction request: '+str(last))

    def converse(self,text,task):
        unsupported=unsupported_request(text)
        if unsupported:
            reply=MESSAGES[unsupported][1 if task.get('language')=='zh' or re.search(r'[\u4e00-\u9fff]',text) else 0]
            packet=dict(plan=dict(action='clarify',updates=[],message=reply),center_mode='unchanged',row_scope='unchanged',accept_defaults=False)
            return parse_plan(packet['plan']),packet,dict(seconds=0.,raw=json.dumps(packet,ensure_ascii=False),normalizations=['Unsupported capability rejected locally'],unsupported_capability=unsupported)
        settings={k:v for k,v in task['settings'].items() if k not in ('training_python','training_repo','training_template','sam3_repo','distro')}
        history=[{'role':m['role'],'text':m['text'][:650]} for m in task['messages'][-6:] if m['text']]
        context=dict(task_kind=task['kind'],task_state=task['state'],next_question=guidance(task),
            language=task.get('language','en'),pending_run=task.get('run_requested',False),settings=settings,
            metadata=task['metadata'],reconstruction_workflow=task.get('sop',{}),recent_conversation=history,latest_user_message=text,explicit_paths=extract_paths(text),actual_results=result_context(task))
        began=time.perf_counter()
        response=self.structured_reply([{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(context,ensure_ascii=False)}])
        folder=STATE_ROOT/'outputs/model_responses';folder.mkdir(parents=True,exist_ok=True)
        (folder/f'{time.time_ns()}.json').write_text(json.dumps({'command':text,'content':response['content']},indent=2,ensure_ascii=False),encoding='utf-8')
        if response.get('stopped_limit'):raise ValueError('The reply was incomplete. Please try a shorter message.')
        data=json.loads(response['content']);normalizations=[]
        data['plan']['updates'],notes=ground_path_updates(data['plan']['updates'],text,task['settings'],PATHS);normalizations.extend(notes)
        binding_task=copy.deepcopy(task)
        if not binding_task['kind'] and data['plan']['action'] in ('reconstruct','segment','train','prepare_dataset','find_center','analyze','try_center','try_angle'):binding_task['kind']=data['plan']['action']
        if binding_task['state'] in ('running','stopping','completed'):binding_task['state']='draft'
        bindings,controls=explicit_answer(text,binding_task)
        if controls:
            data.update(center_mode='unchanged',row_scope='unchanged',accept_defaults=False);data.update(controls)
            data['plan']['updates']=[];data['plan']['action']='set_parameters';normalizations.append('Bound explicit answer')
        if bindings and data['plan']['action'] in ('set_parameters','reconstruct','segment','train','prepare_dataset','find_center','analyze','try_center','try_angle'):
            pairs=data['plan']['updates']
            for key,value in bindings.items():
                existing=[p for p in pairs if p['field']==key]
                if existing:existing[0]['value']=str(value)
                else:pairs.append({'field':key,'value':str(value)})
                normalizations.append('Verified explicit '+key)
        for field in ('center','gpu'):
            if field not in bindings:
                previous=data['plan']['updates'];data['plan']['updates']=[p for p in previous if p['field']!=field]
                if len(previous)!=len(data['plan']['updates']):normalizations.append('Ignored unrequested '+field)
        if data['center_mode']=='known' and 'center' not in bindings:data['center_mode']='unchanged'
        if 'center' in bindings:data['center_mode']='known'
        if extract_paths(text) and not re.search(r'\b(?:rows?|slices?)\b.{0,25}\d|(?:层|切片)\s*\d',text_without_paths(text),re.I):
            previous=data['plan']['updates'];data['plan']['updates']=[p for p in previous if p['field'] not in ('start_row','end_row','search_row','trial_row')]
            if len(previous)!=len(data['plan']['updates']):normalizations.append('Ignored unrequested rows on a selected input')
        plan=parse_plan(data['plan']);normalized=text.replace('\\','/').casefold()
        if 'prompt' in plan.updates:
            target=plan.updates['prompt'].casefold()
            translated=('particle' in target and any(w in text for w in ('颗粒','粒子'))) or ('pore' in target and '孔' in text)
            if target not in normalized and not translated:
                del plan.updates['prompt'];normalizations.append('Removed a feature not supplied by the user')
        if data['center_mode'] not in ('auto','known','unchanged') or data['row_scope'] not in ('all','middle','unchanged') or type(data['accept_defaults']) is not bool:raise ValueError('Invalid conversation response')
        return plan,data,dict(seconds=time.perf_counter()-began,raw=response['content'],normalizations=normalizations)

