import os,sys,json,tempfile,time,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from assistant_lab.conversations import *
from assistant_lab.chat_flow import *
from assistant_lab.results import result_context,answer_result
from assistant_lab.jobs import JobStore,atomic_json
from assistant_lab.chat_window import ChatWindow
from assistant_lab.protocol import Plan

def sourced(kind):
 t=new_task();choose_kind(t,kind);set_source(t,'input_hdf5','D:/data.hdf5');accept_source(t,'input_hdf5','D:/data.hdf5',{'rows':128,'width':128,'projections':91});return t

class PolicyTests(unittest.TestCase):
 def test_only_explicit_requests_or_offered_confirmations_execute(self):
  self.assertTrue(execution_intent('Reconstruct this file.'));self.assertFalse(execution_intent('How would you reconstruct it?'));self.assertFalse(execution_intent('先讨论一下怎么重建，不运行'))
  self.assertFalse(execution_intent('yes'));self.assertTrue(execution_intent('yes',True))
 def test_pasted_path_with_spaces_and_source_kind_is_canonical(self):
  text='Generate trials for "D:\\data folder\\a.hdf5".';self.assertEqual(extract_paths(text),['D:/data folder/a.hdf5'])
  t=new_task();choose_kind(t,'try_center');p=Plan('try_center',{'image_folder':'D:/data folder/a.hdf5'},'');bind_paths(t,p,text);self.assertIn('input_hdf5',p.updates);self.assertNotIn('image_folder',p.updates)
 def test_automatic_search_requires_an_explicit_feature(self):
  t=sourced('find_center');t['search_mode']='auto';apply_defaults(t);self.assertEqual(ready_step(t),'prompt')
  apply_response(t,Plan('set_parameters',{'prompt':'particle'},''));self.assertEqual(ready_step(t),'ready');self.assertEqual(action(t),'find_center')
 def test_center_only_and_reconstruction_are_distinct(self):
  t=sourced('reconstruct');apply_defaults(t);self.assertEqual(ready_step(t),'prompt');self.assertEqual(action(t),'analyze')
  t['settings']['center']=64;t['center_mode']='known';self.assertEqual(action(t),'reconstruct')
 def test_manual_trials_do_not_request_a_sam3_feature(self):
  t=sourced('try_center');self.assertEqual(ready_step(t),'ready');self.assertEqual(action(t),'try_center');self.assertEqual(t['settings']['center'],0)
 def test_unset_setting_does_not_override_the_saved_center(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);job=root/'search';job.mkdir();t=new_task();t['settings']['center']=0;t['jobs']=[{'id':'search','job_dir':str(job),'action':'find_center'}]
   atomic_json(job/'job.json',dict(id='search',settings=t['settings']));atomic_json(job/'job_status.json',dict(state='succeeded',elapsed_seconds=60,result={'recommended_center':1017.,'rounds':7,'unique_evaluations':197}))
   answer,_=answer_result(t,'center');self.assertIn('1017',answer);self.assertNotIn('0.0',answer);self.assertEqual(result_context(t)[0]['recommended_center'],1017)
 def test_missing_results_are_not_reported_as_zero(self):
  t=new_task();answer,_=answer_result(t,'center');self.assertIn('cannot find',answer);self.assertNotIn('0.0',answer)

class ChatRenderTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.app=QApplication.instance() or QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf');cls.app.setFont(QFont('Segoe UI',10))
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.w=ChatWindow(Conversations(self.root/'conversations'),JobStore(self.root/'jobs'),autoload=False);self.w.show();self.pump(.2)
 def pump(self,duration):
  until=time.monotonic()+duration
  while time.monotonic()<until:self.app.processEvents();time.sleep(.005)
 def tearDown(self):self.w.close();self.pump(.05);self.tmp.cleanup()
 def test_appending_messages_keeps_existing_widgets_and_history_position(self):
  task=self.w.current
  for n in range(30):message(task,'assistant',f'Message {n} '+('history line\n'*5))
  self.w.render();self.pump(.3);identity=task['messages'][0]['id'];widget=self.w.views[identity]
  self.w.scroll_animation.stop();bar=self.w.scroll.verticalScrollBar();self.assertGreater(bar.maximum(),500);bar.setValue(120);before=bar.value()
  message(task,'assistant','New result arrived.');self.w.render();self.pump(.3)
  self.assertIs(self.w.views[identity],widget);self.assertLess(abs(bar.value()-before),5)
 def test_actual_worker_progress_is_attached_to_its_reply(self):
  task=self.w.current;message(task,'assistant','Starting the task.');reply=task['messages'][-1]['id'];folder=self.root/'jobs/owned';folder.mkdir();atomic_json(folder/'job_status.json',{'state':'running','phase':'Reconstructing selected rows','completed':1,'total':2});task['jobs']=[dict(id='owned',job_dir=str(folder),action='reconstruct',reply_id=reply,reported=False)];task['state']='running'
  self.w.poll();self.pump(.05);entry=find_entry(task,reply);self.assertEqual(entry['activity'][-1]['text'],'Reconstructing selected rows');self.assertEqual(entry['progress']['done'],1);self.assertTrue(self.w.views[reply].process.isVisible())
 def test_result_question_reads_saved_file_without_running_a_job(self):
  task=self.w.current;folder=self.root/'jobs/search';folder.mkdir();task['jobs']=[dict(id='search',job_dir=str(folder),action='find_center',reported=True)];task['state']='completed'
  atomic_json(folder/'job.json',dict(id='search',settings=task['settings']));atomic_json(folder/'job_status.json',dict(state='succeeded',result={'recommended_center':1017.}))
  with patch.object(self.w.store,'submit',side_effect=AssertionError('Query must not submit')):
   self.w.composer.setPlainText('What rotation center did you find?');self.w.send();self.pump(.4)
  self.assertIn('1017',task['messages'][-1]['text']);self.assertFalse(self.w.busy)
 def test_clear_auto_request_reviews_before_confirmed_analyze(self):
  task=self.w.current;task['settings']['output_root']=str(self.root/'jobs');mark(task,'checkpoint');fake=Mock();fake.running=True
  fake.converse.return_value=(Plan('analyze',{'input_hdf5':'D:/valid.hdf5','prompt':'particle'},'I will find the center and reconstruct.'),{'center_mode':'auto','row_scope':'all','accept_defaults':False},{'seconds':.1})
  job={'id':'owned','job_dir':str(self.root/'jobs/owned'),'action':'analyze'};self.w.model_ready=True
  import h5py,numpy as np
  source=self.root/'auto.h5'
  with h5py.File(source,'w') as h:
   h['exchange/data']=np.ones((7,128,128),np.uint16);h['exchange/data_white']=np.ones((1,128,128),np.uint16)*2;h['exchange/data_dark']=np.zeros((1,128,128),np.uint16);h['exchange/theta']=np.arange(7,dtype=np.float32)*30
  with patch.object(self.w,'model',fake),patch('assistant_lab.chat_window.JobStore.submit',return_value=job) as submit:
   self.w.submit_text(task,f'Automatically reconstruct all rows for "{source}" using tomography, prompt particle.');self.pump(.6)
   self.assertEqual(task['sop']['phase'],'confirm');submit.assert_not_called()
   self.w.submit_text(task,'yes');self.pump(.3)
  self.assertEqual(task['state'],'running');self.assertEqual(submit.call_args.args[0],'analyze');self.assertEqual(submit.call_args.args[1]['start_row'],0);self.assertEqual(submit.call_args.args[1]['end_row'],128)


if __name__=='__main__':unittest.main()
