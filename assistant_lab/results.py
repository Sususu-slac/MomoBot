"""Read factual task outputs for follow-up conversation; never substitute defaults."""
from pathlib import Path
import re
from .path_rules import path_key
from .jobs import read_json
from .chat_flow import say

def result_context(task):
    records=[]
    for job in task.get('jobs',[])[-4:]:
        folder=Path(job['job_dir']);config=read_json(folder/'job.json')
        if config.get('id')!=job['id']:continue
        status=read_json(folder/'job_status.json');result=status.get('result') or read_json(folder/'results/result.json')
        center=result.get('center_search',result)
        if not center.get('recommended_center'):center=read_json(folder/'results/center_search/summary.json') or center
        artifacts={key:str(folder/'results/center_search'/name) for key,name in {'curve':'adaptive_search.png','best_image':'best_input.png','overlay':'best_overlay.png','scores':'scores.csv','reconstruction':'best_reconstruction.tiff'}.items() if (folder/'results/center_search'/name).is_file()}
        cfg=config.get('settings',{})
        source_stat=task.get('sop',{}).get('source_stat')
        if source_stat and job['action'] in ('reconstruct','analyze','find_center','try_center','try_angle') and (config.get('source_stat') or job.get('source_stat'))!=source_stat:continue
        current=task.get('settings',{}).get('input_hdf5')
        if current and job['action'] in ('reconstruct','analyze','find_center','try_center','try_angle') and path_key(cfg.get('input_hdf5',''))!=path_key(current):continue
        row=cfg.get('search_row')
        candidate=center.get('recommended_metrics',{}).get('file','')
        match=re.search(r'recon_slice(\d+)_',candidate)
        if match:row=int(match[1])
        record=dict(action=job['action'],state=status.get('state'),elapsed_seconds=status.get('elapsed_seconds'),
            gpu=cfg.get('gpu'),method=cfg.get('method'),prompt=cfg.get('prompt'),input_checkpoint=cfg.get('checkpoint'),
            reconstruction_rows=[cfg.get('start_row'),cfg.get('end_row')] if job['action'] in ('reconstruct','analyze') else None,
            output=status.get('output',str(folder/'results')),artifacts=artifacts,source=cfg.get('input_hdf5') or cfg.get('image_folder') or cfg.get('dataset'),
            recommended_center=center.get('recommended_center'),entered_center_used=result.get('center') if job['action']=='reconstruct' else None,geometry=cfg.get('geometry'),lamino_angle=cfg.get('lamino_angle'),
            search_row=row,rounds=center.get('rounds'),evaluated_points=center.get('unique_evaluations'),score_method=center.get('score_method'),
            best_score=center.get('recommended_metrics',{}).get('confidence_reward'),final_step=center.get('final_step'),
            recommendation_status=center.get('recommendation_status'),ambiguity=center.get('ambiguity'),
            reconstructed_slices=result.get('reconstructed_slices',result.get('slices')),segmented_images=result.get('images',result.get('segmented_slices',result.get('segmented_images'))),
            checkpoint=result.get('checkpoint'),inference_checkpoint=result.get('inference_checkpoint'),trial_candidates=result.get('candidates'),
            user_review=job.get('user_review'),result_file=str(folder/'results/result.json'))
        if job['action'] in ('try_center','try_angle'):record['trial']={k:result.get(k) for k in ('search_kind','trial_row','anchor','half_width','step','candidates')}
        records.append({k:v for k,v in record.items() if v is not None})
    return records

def query_type(text):
    lower=text.lower()
    if re.search(r'what.*mean|definition|是什么意思|概念|解释.*中心',lower):return None
    if re.search(r'open|show|打开|看一下|看看',lower):
        if re.search(r'(?:result|output)\s*(?:folder)?|结果|文件夹',lower) and not re.search(r'curve|image|slice|曲线|图片|图像',lower):return 'open_folder'
        if re.search(r'curve|曲线',lower):return 'open_curve'
        if re.search(r'best.*(?:image|slice|recon)|最佳.*(?:图|层|重建)',lower):return 'open_best_image'
    if re.search(r'what.*cent(?:er|re)|which.*cent(?:er|re)|cent(?:er|re).*(?:result|value)|already.*search|did.*find|中心.*(?:多少|结果|找到)|结果.*中心|已经.*找',lower):return 'center'
    if re.search(r'how long|time.*(?:take|spent)|耗时|用了多久|多长时间',lower):return 'time'
    if re.search(r'which.*slice|which.*row|哪.*(?:层|slice)|第几层',lower):return 'slice'
    if re.search(r'why.*(?:this|that|center)|为什么.*(?:中心|选)|怎么.*评分',lower):return 'score'
    if re.search(r'where.*result|where.*output|结果.*(?:哪里|在哪)|输出.*(?:哪里|在哪)',lower):return 'output'
    return None

def answer_result(task,query):
    records=result_context(task)
    if query=='center':records=[r for r in records if r.get('state')=='succeeded']
    relevant=(next((r for r in reversed(records) if r.get('recommended_center') is not None),records[-1] if records else None)
              if query in ('slice','score','open_curve','open_best_image') else records[-1] if records else None)
    if relevant is None:return say(task,'I cannot find a saved result for this task yet. No rotation-center result is available.','当前任务尚未找到已保存的结果，暂时没有可报告的旋转中心结果。'),None
    r=relevant
    if query=='open_folder':
        path=r['output'];return say(task,'Results: ','结果目录：')+path,path
    if query.startswith('open_'):
        key='curve' if query=='open_curve' else 'best_image';path=r.get('artifacts',{}).get(key)
        return (say(task,'Opening the saved result: ','正在打开已保存的结果：')+path,path) if path else (say(task,'This task has no saved '+key+' artifact.','这个任务没有保存对应的曲线或图片。'),None)
    if query=='center':
        if r.get('recommended_center') is not None:
            value=r['recommended_center'];text=say(task,f'The rotation center found by the algorithm is {value:g} pixels.',f'算法找到的旋转中心是 {value:g} 像素。')
            if r.get('rounds') is not None:text+=say(task,f" The search used {r['rounds']} rounds and {r.get('evaluated_points','?')} candidates.",f" 共搜索 {r['rounds']} 轮、{r.get('evaluated_points','?')} 个候选点。")
        elif r.get('entered_center_used',0)>0:text=say(task,f"This reconstruction used the entered center {r['entered_center_used']:g} pixels. It was not an automatic center-search result.",f"这个重建任务使用了你输入的中心 {r['entered_center_used']:g} 像素；它不是自动查找得到的结果。")
        elif task.get('sop',{}).get('center_valid') and task.get('sop',{}).get('selection',{}).get('quantity')=='center':
            value=task['settings']['center'];text=say(task,f'You selected rotation center {value:g} pixels from the trial results.',f'你从候选结果中选择的旋转中心是 {value:g} 像素。')
        else:text=say(task,'No completed center-search result is saved for this task. The unset value 0 is not a search result.','当前任务没有保存已完成的中心查找结果。未设置时的 0 不是查找结果。')
    elif query=='time' and r.get('state') not in ('succeeded','failed','cancelled'):
        text=say(task,f"Elapsed so far: {r.get('elapsed_seconds',0):.1f} seconds; the task is still running.",f"目前已运行 {r.get('elapsed_seconds',0):.1f} 秒，任务尚未结束。")
    elif query=='time':text=say(task,f"The task took {r.get('elapsed_seconds',0):.1f} seconds in total, including its saved stages.",f"这个任务总共用了 {r.get('elapsed_seconds',0):.1f} 秒，包含该任务的全部执行阶段。")
    elif query=='slice':text=say(task,f"The recorded center-search detector row is {r['search_row']}.",f"记录中的中心搜索使用的是第 {r['search_row']} 层（从 0 开始计数）。") if r.get('search_row') is not None else say(task,'The saved result does not record a center-search row.','这个结果没有记录中心搜索使用的层号。')
    elif query=='score':
        text=say(task,f"The saved method is {r.get('score_method','not recorded')}; the recommended center is {r.get('recommended_center','not recorded')}. The recorded recommendation status is {r.get('recommendation_status','not recorded')}.",f"保存的评分方法是 {r.get('score_method','未记录')}，推荐中心为 {r.get('recommended_center','未记录')}，峰值判断为 {r.get('recommendation_status','未记录')}。")
        if r.get('best_score') is not None:text+=say(task,f" The candidate's confidence-weighted score is {r['best_score']:.3f}.",f" 该候选点的置信度加权分数为 {r['best_score']:.3f}。")
    else:text=say(task,'Results: ','结果目录：')+r['output']
    return text,None
