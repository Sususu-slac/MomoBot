import os,sys,time,json,copy
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from assistant_lab.config import ROOT,SAMPLE,IMAGES
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations,step
from assistant_lab.jobs import JobStore,read_json
root=ROOT/('test_outputs/live_'+str(time.time_ns()));root.mkdir(parents=True,exist_ok=True)
app=QApplication([])
for f in ['segoeui.ttf','segoeuib.ttf','seguisym.ttf']:QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
app.setFont(QFont('Segoe UI',10));app.setStyle('Fusion')
w=ChatWindow(Conversations(root/'conversations'),JobStore(root/'jobs'),autoload=False);w.show();app.processEvents();report={'commands':[],'jobs':[]}
def wait_request():
 deadline=time.monotonic()+180
 while w.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
 assert not w.busy,'Request timed out'
 app.processEvents()
def send(text,expected):
 w.composer.setPlainText(text);w.send();wait_request();actual=step(w.current);report['commands'].append(dict(command=text,expected_step=expected,actual_step=actual,messages=w.current['messages'][-2:]));print('COMMAND',text,'STEP',actual,flush=True);assert actual==expected,w.current['messages'][-3:]
def source(field,path,expected):
 with patch('assistant_lab.chat_window.QFileDialog.getOpenFileName',return_value=(path,'')),patch('assistant_lab.chat_window.QFileDialog.getExistingDirectory',return_value=path):w.browse(field)
 wait_request();assert step(w.current)==expected,w.current['messages'][-3:]
def run_task():
 task=w.current;task['settings']['output_root']=str(root/'jobs');w.start_task(task);assert task['state']=='running',task['messages'][-2:]
 job=task['jobs'][-1];deadline=time.monotonic()+300
 while time.monotonic()<deadline:
  app.processEvents();s=read_json(Path(job['job_dir'])/'job_status.json')
  if s.get('state') in ('succeeded','failed','stopped'):
   w.poll();report['jobs'].append({**job,**s});print('JOB',job['action'],s.get('state'),s.get('elapsed_seconds'),s.get('error',''),flush=True);assert s['state']=='succeeded',s.get('error');return
  time.sleep(.05)
 raise TimeoutError('Scientific test is still running; worker left running')
try:
 w.grab().save(str(root/'welcome.png'));w.load_model();wait_request();assert w.model_ready
 send('I want to reconstruct tomography data.','input_hdf5');source('input_hdf5',SAMPLE,'center_mode')
 send('The rotation center is 1028.75 pixels.','rows')
 send('Reconstruct start row 1023 end row 1025 using FourierRec on GPU 1.','ready')
 w.grab().save(str(root/'reconstruction_review.png'));run_task()
 w.new_task();send('I want to segment images.','image_folder');source('image_folder',IMAGES,'prompt')
 send('particle','limit');send('Only 1 image, with confidence 25 percent.','ready')
 w.grab().save(str(root/'segmentation_review.png'));run_task()
 w.new_task();send('I want to fine-tune SAM3.','dataset')
 data='D:/BL62_Assistant_Lab/test_outputs/validation_20261027_150001/jobs/20261027_150004_0c05f607_prepare_dataset/results/dataset'
 source('dataset',data,'epochs');send('2 epochs with batch size 1.','ready')
 assert not w.current['jobs'],'Training must not auto-start'
 send('What does an epoch mean?','ready');assert w.current['settings']['epochs']==2
 w.grab().save(str(root/'training_conversation.png'));report['passed']=True
finally:
 wait_request();w.close();app.processEvents();(root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('REPORT',root/'report.json',flush=True)
