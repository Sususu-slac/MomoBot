"""Task deletion persists and cannot launch delayed work or delete result data."""
import os,sys,time,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QMessageBox
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations
from assistant_lab.jobs import JobStore,atomic_json

class TaskDeletionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.repo=Conversations(self.root/'conversations');self.store=JobStore(self.root/'jobs')
  self.window=ChatWindow(self.repo,self.store,autoload=False)
 def tearDown(self):
  self.window.busy=False;self.window.close();self.app.processEvents();self.tmp.cleanup()
 def delete(self,identity=None):
  with patch('assistant_lab.chat_window.QMessageBox.question',return_value=QMessageBox.Yes):return self.window.delete_task(identity)
 def test_delete_current_selects_other_and_survives_restart(self):
  first=self.window.current;self.window.new_task();deleted=self.window.current
  self.window.composer.setPlainText('draft that must disappear')
  self.assertTrue(self.delete());self.assertEqual(self.window.current_id,first['id'])
  self.assertFalse((self.repo.root/(deleted['id']+'.json')).exists())
  self.window.close();self.window=ChatWindow(self.repo,self.store,autoload=False)
  self.assertNotIn(deleted['id'],self.window.tasks);self.assertEqual(len(self.window.tasks),1)
 def test_deleting_last_task_keeps_empty_list_after_restart_and_can_create_new(self):
  deleted=self.window.current
  self.assertTrue(self.delete());self.assertEqual(self.window.task_list.count(),0)
  self.assertIsNone(self.window.current);self.assertFalse(self.window.send_btn.isEnabled());self.assertFalse(self.window.attach_btn.isEnabled())
  self.window.close();self.window=ChatWindow(self.repo,self.store,autoload=False)
  self.assertEqual(self.window.tasks,{});self.assertEqual(self.window.task_list.count(),0)
  self.window.new_task();self.assertNotEqual(self.window.current_id,deleted['id']);self.assertTrue(self.window.send_btn.isEnabled())
 def test_delete_inactive_task_preserves_current_draft(self):
  old=self.window.current;self.window.new_task();identity=self.window.current_id
  self.window.composer.setPlainText('keep this draft')
  self.assertTrue(self.delete(old['id']));self.assertEqual(self.window.current_id,identity)
  self.assertEqual(self.window.composer.toPlainText(),'keep this draft')
 def test_visible_delete_button_is_connected(self):
  identity=self.window.current_id
  with patch('assistant_lab.chat_window.QMessageBox.question',return_value=QMessageBox.Yes):self.window.delete_btn.click()
  self.assertNotIn(identity,self.window.tasks);self.assertFalse((self.repo.root/(identity+'.json')).exists())
 def test_cancel_preserves_record(self):
  identity=self.window.current_id
  with patch('assistant_lab.chat_window.QMessageBox.question',return_value=QMessageBox.No):self.assertFalse(self.window.delete_task())
  self.assertIn(identity,self.window.tasks);self.assertTrue((self.repo.root/(identity+'.json')).exists())
 def test_running_task_cannot_be_deleted(self):
  for state,busy in [('running',False),('stopping',False)]:
   self.window.current['state']=state;self.window.busy=busy
   with patch('assistant_lab.chat_window.QMessageBox.information'),patch('assistant_lab.chat_window.QMessageBox.question') as ask:
    self.assertFalse(self.window.delete_task());ask.assert_not_called()
   self.assertTrue((self.repo.root/(self.window.current_id+'.json')).exists())
  self.window.busy=False
 def test_can_delete_while_model_is_loading(self):
  self.window.busy=True;self.window.update_send_enabled()
  self.assertTrue(self.window.delete_btn.isEnabled());self.assertTrue(self.delete())
  self.assertFalse(self.window.tasks);self.window.busy=False
 def test_deleting_during_background_reply_discards_the_late_callback(self):
  task=self.window.current;called=[]
  self.window.background(lambda:(time.sleep(.1) or 'late'),lambda value:called.append(value),task['id'])
  self.assertTrue(self.window.delete_btn.isEnabled());self.assertTrue(self.delete())
  deadline=time.monotonic()+3
  while self.window.busy and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
  self.assertFalse(self.window.busy);self.assertEqual(called,[])
  self.assertFalse((self.repo.root/(task['id']+'.json')).exists())
 def test_active_worker_blocks_deletion_even_when_task_state_is_stale(self):
  job=self.root/'jobs/active';job.mkdir(parents=True);atomic_json(job/'job_status.json',{'state':'running'})
  self.window.current['jobs']=[dict(id='active',action='reconstruct',job_dir=str(job))]
  with patch('assistant_lab.chat_window.QMessageBox.information'):self.assertFalse(self.window.delete_task())
 def test_rechecks_state_after_confirmation(self):
  def answer(*args):self.window.current['state']='running';return QMessageBox.Yes
  with patch('assistant_lab.chat_window.QMessageBox.question',side_effect=answer),patch('assistant_lab.chat_window.QMessageBox.information'):
   self.assertFalse(self.window.delete_task())
 def test_removes_telegram_references_and_keeps_other_subscriptions(self):
  identity=self.window.current_id;control=self.window.telegram
  control.settings.update(task_id=identity,subscriptions=[identity,'other'])
  control.seen={(identity,'m'):'old',('other','m'):'keep'};control.sent_at={(identity,'m'):1};control.stickers_seen={(identity,'m')}
  self.assertTrue(self.delete());cfg=control.settings.read()
  self.assertIsNone(cfg['task_id']);self.assertEqual(cfg['subscriptions'],['other'])
  self.assertEqual(control.seen,{('other','m'):'keep'});self.assertFalse(control.sent_at);self.assertFalse(control.stickers_seen)
 def test_queued_callbacks_and_saves_cannot_restore_deleted_task(self):
  task=self.window.current;task['run_requested']=True
  self.assertTrue(self.delete());self.repo.save(task);self.window.save(task)
  with patch.object(self.window.store,'submit') as submit,patch.object(self.window,'background') as background:
   self.window.advance(task,None);self.window.start_task(task);self.window.submit_text(task,'Reconstruct everything')
   submit.assert_not_called();background.assert_not_called()
  self.window.fail(task['id'],'late error')
  self.assertFalse((self.repo.root/(task['id']+'.json')).exists())
 def test_results_and_original_inputs_are_preserved(self):
  job=self.root/'jobs/completed';(job/'results').mkdir(parents=True)
  result=job/'results/recon.tiff';result.write_bytes(b'reconstruction')
  original=self.root/'input.h5';original.write_bytes(b'input')
  atomic_json(job/'job_status.json',{'state':'succeeded'})
  self.window.current['jobs']=[dict(id='completed',action='reconstruct',job_dir=str(job))]
  self.assertTrue(self.delete());self.assertEqual(result.read_bytes(),b'reconstruction');self.assertEqual(original.read_bytes(),b'input')
 def test_file_error_keeps_task_in_list(self):
  identity=self.window.current_id
  with patch.object(self.repo,'delete',side_effect=PermissionError('locked')),patch('assistant_lab.chat_window.QMessageBox.question',return_value=QMessageBox.Yes),patch('assistant_lab.chat_window.QMessageBox.warning'):
   self.assertFalse(self.window.delete_task())
  self.assertIn(identity,self.window.tasks);self.assertFalse(self.window.current.get('_deleted'))
 def test_repository_rejects_path_traversal(self):
  for identity in ['../input','..\\input','', '..']:
   with self.assertRaises(ValueError):self.repo.delete(identity)
if __name__=='__main__':unittest.main(verbosity=2)
