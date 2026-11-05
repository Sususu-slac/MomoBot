"""Fresh startup, lazy task creation and scrolling after delayed Qt layouts."""
import os,tempfile,time,unittest
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QAbstractSlider
from PySide6.QtCore import QTimer
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations,message
from assistant_lab.jobs import JobStore

class ChatNavigationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.app=QApplication.instance() or QApplication([]);cls.app.setStyle('Fusion')
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.repo=Conversations(self.root/'conversations');self.store=JobStore(self.root/'jobs');self.w=None
 def open(self):
  self.w=ChatWindow(self.repo,self.store,autoload=False);self.w.show();self.pump();return self.w
 def pump(self,seconds=.15):
  deadline=time.monotonic()+seconds
  while time.monotonic()<deadline:self.app.processEvents();time.sleep(.005)
 def tearDown(self):
  self.pump(.03)
  if self.w:self.w.close();self.pump(.03)
  self.tmp.cleanup()
 def long_chat(self):
  self.open();self.w.new_task();t=self.w.current
  for n in range(22):message(t,'assistant',f'Message {n}\n'+('A long line of image reconstruction information. '*5+'\n')*3)
  self.w.render();bar=self.w.scroll.verticalScrollBar();deadline=time.monotonic()+3
  while bar.maximum()<500 and time.monotonic()<deadline:self.pump(.05)
  self.pump(.15);return t,bar
 def test_first_start_is_writable_without_creating_a_task(self):
  self.open();self.assertIsNone(self.w.current);self.assertEqual(self.repo.all(),[]);self.assertEqual(self.w.heading.text(),'New chat');self.assertTrue(self.w.send_btn.isEnabled());self.assertTrue(self.w.attach_btn.isEnabled())
 def test_saved_history_is_listed_but_not_opened(self):
  old=self.repo.create();old['draft']='keep my previous draft';message(old,'user','Previous conversation');self.repo.save(old)
  self.open();self.assertIsNone(self.w.current);self.assertEqual(self.w.task_list.count(),1);self.assertIsNone(self.w.task_list.currentItem());self.assertEqual(self.w.composer.toPlainText(),'');self.assertEqual(self.w.views,{});self.assertEqual(self.repo.all()[0]['draft'],'keep my previous draft')
 def test_first_message_creates_one_task_then_reuses_it(self):
  old=self.repo.create();old_id=old['id'];self.open();self.w.composer.setPlainText('Hi');self.w.send();self.pump();task=self.w.current;self.assertNotEqual(task['id'],old_id);self.assertEqual(len(self.repo.all()),2);self.assertEqual([m['text'] for m in task['messages'] if m['role']=='user'],['Hi'])
  self.w.composer.setPlainText('hello');self.w.send();self.pump();self.assertEqual(self.w.current_id,task['id']);self.assertEqual(len(self.repo.all()),2)
 def test_reopening_returns_to_fresh_chat_without_discarding_history(self):
  self.open();self.w.composer.setPlainText('Hi');self.w.send();self.pump();old=self.w.current_id;self.w.close();self.pump(.03);self.open()
  self.assertIsNone(self.w.current);self.assertIn(old,self.w.tasks);self.assertEqual(len(self.repo.all()),1)
  self.w.composer.setPlainText('Hello');self.w.send();self.pump();self.assertNotEqual(self.w.current_id,old);self.assertEqual(len(self.repo.all()),2)
 def test_blank_input_and_refresh_do_not_create_tasks_or_erase_typing(self):
  self.open();self.w.composer.setPlainText('   ');self.w.send();self.assertEqual(self.repo.all(),[])
  self.w.composer.setPlainText('Unsent new request');self.w.render();self.w.poll();self.pump();self.assertEqual(self.w.composer.toPlainText(),'Unsent new request');self.assertEqual(self.repo.all(),[])
 def test_explicit_new_task_button_is_still_available(self):
  self.open();self.w.new_btn.click();identity=self.w.current_id;self.assertIsNotNone(identity);self.w.composer.setPlainText('Hi');self.w.send();self.pump();self.assertEqual(self.w.current_id,identity);self.assertEqual(len(self.repo.all()),1)
 def test_history_can_be_opened_manually_with_its_draft(self):
  old=self.repo.create();old['draft']='saved draft';self.repo.save(old);self.open();self.w.task_list.setCurrentRow(0);self.pump();self.assertEqual(self.w.current_id,old['id']);self.assertEqual(self.w.composer.toPlainText(),'saved draft')
 def test_attachment_cancellation_on_fresh_page_creates_no_empty_task(self):
  self.open()
  with patch('assistant_lab.chat_window.QFileDialog.getOpenFileName',return_value=('','')):self.w.browse('input_hdf5')
  self.assertIsNone(self.w.current);self.assertEqual(self.repo.all(),[])
 def test_selected_attachment_can_create_a_task_from_the_fresh_page(self):
  self.open()
  with patch('assistant_lab.chat_window.QFileDialog.getExistingDirectory',return_value=str(self.root)),patch.object(self.w,'inspect') as inspect:self.w.browse('image_folder')
  self.assertEqual(self.w.current['kind'],'segment');self.assertEqual(len(self.repo.all()),1);inspect.assert_called_once()
 def test_first_reconstruction_message_still_uses_model_first(self):
  self.open();fake=Mock();fake.running=True;self.w.model=fake;self.w.model_ready=True
  fake.understand_reconstruction.return_value=({'intent':'request','operation':'reconstruct','mode':'unchanged','row_scope':'unchanged','updates':{},'selection':'','query':'none','message':'Plan reconstruction.'},{'model_called':True})
  self.w.composer.setPlainText('Please reconstruct my data');self.w.send();self.pump(.5);fake.understand_reconstruction.assert_called_once();self.assertEqual(len(self.repo.all()),1);self.assertEqual(self.w.current['sop']['phase'],'path');self.assertFalse(self.w.current['jobs'])
 def test_latest_reply_and_later_text_growth_stay_visible(self):
  t,bar=self.long_chat();self.assertGreater(bar.maximum(),500);self.assertLessEqual(bar.maximum()-bar.value(),2)
  message(t,'assistant','Working…');entry=t['messages'][-1];self.w.render()
  def expand():entry['text']='Finished\n'+('Detailed result with a line that wraps. '*12+'\n')*12;self.w.render()
  QTimer.singleShot(35,expand);self.pump(.4);self.assertLessEqual(bar.maximum()-bar.value(),2)
  self.w.resize(920,660);self.pump(.25);self.assertLessEqual(bar.maximum()-bar.value(),2)
 def test_sending_from_old_history_resumes_following_latest(self):
  t,bar=self.long_chat();bar.setSliderPosition(100);bar.triggerAction(QAbstractSlider.SliderMove);self.assertFalse(self.w.follow_latest);self.w.composer.setPlainText('Hi');self.w.send();self.pump(.3);self.assertTrue(self.w.follow_latest);self.assertLessEqual(bar.maximum()-bar.value(),2)
 def test_scrolled_history_does_not_jump_when_a_reply_arrives(self):
  t,bar=self.long_chat();bar.setSliderPosition(100);bar.triggerAction(QAbstractSlider.SliderMove);before=bar.value();message(t,'assistant','A new result arrived.');self.w.render();self.pump(.25);self.assertLess(abs(bar.value()-before),3)
 def test_switching_tasks_restores_history_position_and_follow_state(self):
  t,bar=self.long_chat();bar.setSliderPosition(100);bar.triggerAction(QAbstractSlider.SliderMove);self.w.new_task();self.pump();self.w.select_task(t['id']);self.pump(.25);self.assertFalse(self.w.follow_latest);self.assertLess(abs(bar.value()-100),3)

if __name__=='__main__':unittest.main()
