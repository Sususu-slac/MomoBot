import os,sys,time,json
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from assistant_lab.config import ROOT,SAMPLE
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations
from assistant_lab.chat_flow import ready_step
from assistant_lab.jobs import JobStore,read_json
root=sorted((ROOT/'test_outputs').glob('chat030_*'))[-1];report=read_json(root/'report.json');app=QApplication([])
for f in ['segoeui.ttf','segoeuib.ttf','seguisym.ttf','msyh.ttc']:QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
app.setFont(QFont('Segoe UI',10));app.setStyle('Fusion')
w=ChatWindow(Conversations(root/'conversations'),JobStore(root/'jobs'),autoload=False);w.show()
def pump(t=.1):
 end=time.monotonic()+t
 while time.monotonic()<end:app.processEvents();time.sleep(.01)
def idle():
 end=time.monotonic()+180;since=None
 while time.monotonic()<end:
  pump(.05)
  if not w.busy:
   since=since or time.monotonic()
   if time.monotonic()-since>.4:return
  else:since=None
 raise TimeoutError('Chat request timed out')
def send(text):
 w.composer.setPlainText(text);w.send();idle();task=w.current;print('TURN',text,'=>',task['kind'],task['state'],ready_step(task),flush=True);report['commands'].append({'text':text,'kind':task['kind'],'state':task['state'],'step':ready_step(task)});return task
def finish():
 task=w.current;assert task['jobs'],task['messages'][-2:];job=task['jobs'][-1];end=time.monotonic()+480
 while time.monotonic()<end:
  pump();s=read_json(Path(job['job_dir'])/'job_status.json')
  if s.get('state') in ('succeeded','failed','stopped'):
   w.poll();print('JOB',job['action'],s['state'],s.get('elapsed_seconds'),s.get('error',''),flush=True);report['jobs'].append({**job,**s});assert s['state']=='succeeded',s.get('error');return
 raise TimeoutError('Scientific task left running')
try:
 # Recover the real Chinese segmentation task completed after the former monitor's encoding error.
 for task in w.tasks.values():
  if task['kind']=='segment' and task['jobs']:
   s=read_json(Path(task['jobs'][-1]['job_dir'])/'job_status.json');assert s['state']=='succeeded',s
   assert task['settings']['max_images']==1 and task['settings']['confidence']==.25
   if not any(j['id']==task['jobs'][-1]['id'] for j in report['jobs']):report['jobs'].append({**task['jobs'][-1],**s})
   print('RECOVERED Chinese segmentation',s['state'],flush=True)
 w.load_model();idle();assert w.model_ready;w.new_task();w.current['settings']['output_root']=str(root/'jobs')
 task=send(f'Automatically find the rotation center only for "{SAMPLE}", search range 1027 to 1030, initial step 1, target step 0.25.')
 assert task['kind']=='find_center' and ready_step(task)=='prompt' and not task['jobs'],task['messages'][-2:]
 assert task['settings']['range_low']==1027 and task['settings']['range_high']==1030,task['settings']
 task=send('particle');assert task['state']=='running',task['messages'][-2:];finish()
 assert task['jobs'][-1]['action']=='find_center'
 saved=read_json(Path(task['jobs'][-1]['job_dir'])/'job_status.json')['result']['recommended_center']
 task=send('What rotation center did you find?');assert str(int(saved)) in task['messages'][-1]['text'],task['messages'][-1]
 assert len(task['jobs'])==1
 w.grab().save(str(root/'center_result_with_activity.png'))
 w.new_task();w.current['settings']['output_root']=str(root/'jobs')
 fixture=root/'small_exchange.hdf5';task=send(f'How would you reconstruct "{fixture}"? Explain only, do not run.')
 assert not task['jobs'] and not task.get('run_requested')
 report['passed']=True
finally:
 idle();w.close();pump();(root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print('REPORT',root/'report.json',flush=True)
