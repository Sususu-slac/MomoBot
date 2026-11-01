import os,sys,time,json,shutil
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.stdout.reconfigure(encoding="utf-8");sys.stderr.reconfigure(encoding="utf-8")
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from assistant_lab.config import ROOT,SAMPLE,IMAGES
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations
from assistant_lab.jobs import JobStore,read_json
from assistant_lab.chat_flow import ready_step
root=ROOT/('test_outputs/chat030_'+str(time.time_ns()));root.mkdir(parents=True)
# A cropped scientific input exercises both trial backends without a full-volume run.
import h5py
fixture=root/'small_exchange.hdf5'
with h5py.File(SAMPLE,'r') as src,h5py.File(fixture,'w') as dst:
 e=dst.create_group('exchange');e.create_dataset('data',data=src['exchange/data'][::10,960:1088,960:1088])
 for name in ['data_white','data_dark']:e.create_dataset(name,data=src['exchange/'+name][:,960:1088,960:1088])
 e.create_dataset('theta',data=src['exchange/theta'][::10])
images=root/'images';images.mkdir()
for p in sorted(Path(IMAGES).glob('*.png'))[:2]:shutil.copy2(p,images/p.name)
app=QApplication([])
for f in ['segoeui.ttf','segoeuib.ttf','seguisym.ttf','msyh.ttc']:QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
app.setFont(QFont('Segoe UI',10));app.setStyle('Fusion')
w=ChatWindow(Conversations(root/'conversations'),JobStore(root/'jobs'),autoload=False);w.show();app.processEvents()
report={'commands':[],'jobs':[]};w.current['settings']['output_root']=str(root/'jobs')
def pump(seconds=.3):
 end=time.monotonic()+seconds
 while time.monotonic()<end:app.processEvents();time.sleep(.01)
def wait_idle():
 deadline=time.monotonic()+180;idle=None
 while time.monotonic()<deadline:
  app.processEvents()
  if not w.busy:
   idle=idle or time.monotonic()
   if time.monotonic()-idle>.4:return
  else:idle=None
  time.sleep(.01)
 raise TimeoutError('Conversation request timed out')
def fresh():
 w.new_task();w.current['settings']['output_root']=str(root/'jobs')
def send(text):
 w.composer.setPlainText(text);w.send();wait_idle();t=w.current
 report['commands'].append({'text':text,'kind':t['kind'],'state':t['state'],'step':ready_step(t),'settings':dict(t['settings'])})
 print('TURN',text,'=>',t['kind'],t['state'],ready_step(t),flush=True);return t
def finish():
 task=w.current;assert task['jobs'],task['messages'][-2:]
 job=task['jobs'][-1];deadline=time.monotonic()+480
 while time.monotonic()<deadline:
  pump(.1);s=read_json(Path(job['job_dir'])/'job_status.json')
  if s.get('state') in ('succeeded','failed','stopped'):
   w.poll();report['jobs'].append({**job,**s});print('JOB',job['action'],s.get('state'),s.get('elapsed_seconds'),s.get('error',''),flush=True)
   assert s['state']=='succeeded',s.get('error');assert task['messages'][-1].get('activity'),task['messages'][-1]
   return
 raise TimeoutError('Scientific job still running; left running')
try:
 w.grab().save(str(root/'welcome.png'));w.load_model();wait_idle();assert w.model_ready
 t=send(f'Reconstruct "{fixture}" with center 64, start row 63 end row 65 on GPU 1.')
 assert t['state']=='running' and t['settings']['start_row']==63 and t['settings']['end_row']==65,t['messages'][-2:];w.grab().save(str(root/'reconstruction_running.png'));finish()
 fresh();t=send(f'Generate trial center reconstructions for "{fixture}", center 64, trial width 1, trial step 1, trial row 64.')
 assert t['kind']=='try_center',t['messages'][-2:];finish()
 fresh();t=send(f'Generate lamino angle trial reconstructions for "{fixture}", fixed center 64, angle 20, trial width 0.25, trial step 0.25, trial row 64.')
 assert t['kind']=='try_angle',t['messages'][-2:];finish()
 fresh();t=send(f'分割 "{images}" 里的前1张图片，prompt particle，置信度25%。')
 assert t['kind']=='segment' and t['settings']['max_images']==1 and t['settings']['confidence']==.25,t['messages'][-2:];finish()
 fresh();t=send(f'Automatically find the rotation center only for "{SAMPLE}", search range 1027 to 1030, initial step 1, target step 0.25.')
 assert t['kind']=='find_center' and ready_step(t)=='prompt' and not t['jobs'],t['messages'][-2:]
 t=send('particle');assert t['state']=='running',t['messages'][-2:];finish()
 assert t['jobs'][-1]['action']=='find_center';w.grab().save(str(root/'center_result.png'))
 fresh();t=send(f'How would you reconstruct "{fixture}"? Explain only, do not run.')
 assert not t['jobs'] and not t.get('run_requested'),t['messages'][-2:];report['passed']=True
finally:
 wait_idle();w.close();pump();(root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print('REPORT',root/'report.json',flush=True)
