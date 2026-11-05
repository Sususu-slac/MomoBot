import os,sys,json,time,tempfile,unittest,copy,io,urllib.error,threading
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QPushButton,QLineEdit
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from assistant_lab.telegram_bridge import TelegramBridge,TelegramSettings,TelegramAPI,TelegramError
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations,choose_kind,message,mark
from assistant_lab.chat_flow import activity,finish_activity
from assistant_lab.jobs import JobStore,atomic_json
from assistant_lab.protocol import Plan
from assistant_lab.telegram_setup import qr_image

def decode_qr(image):
 import cv2,numpy as np
 from PySide6.QtGui import QImage
 image=image.convertToFormat(QImage.Format_RGBA8888)
 data=np.frombuffer(image.constBits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4)
 return cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(data,cv2.COLOR_RGBA2BGR))[0]

class FakeBridge:
 def __init__(self):self.texts=[];self.images=[];self.stickers=[]
 def send_text(self,text,key=None):self.texts.append((text,key));return True
 def send_image(self,path):self.images.append(path);return True
 def send_sticker(self,path,key=None):self.stickers.append((path,key));return True
 def stop(self):pass

class TelegramAccessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.settings=TelegramSettings(Path(self.tmp.name)/'telegram.json');self.bridge=TelegramBridge(self.settings,api=Mock());self.bridge.send_text=Mock();self.bridge.incoming=Mock();self.bridge.paired=Mock()
 def tearDown(self):self.bridge.stop();self.tmp.cleanup()
 def update(self,n,text,user=123,kind='private',date=None):
  return dict(update_id=n,message={'date':int(time.time()) if date is None else date,'text':text,'message_id':n,'chat':{'id':user,'type':kind},'from':{'id':user,'is_bot':False}})
 def pair(self):
  code=self.bridge.new_pair_code();self.bridge.handle_update(self.update(1,'/start '+code));self.assertEqual(self.settings.read()['owner_id'],123)
 def test_owner_pairing_is_required_and_single_use(self):
  code=self.bridge.new_pair_code()
  self.bridge.handle_update(self.update(1,'reconstruct D:/private.hdf5'));self.bridge.incoming.emit.assert_not_called()
  self.bridge.handle_update(self.update(2,'/start wrong'));self.assertFalse(self.settings.read().get('owner_id'))
  self.bridge.handle_update(self.update(3,'/start '+code,kind='group'));self.assertFalse(self.settings.read().get('owner_id'))
  self.bridge.handle_update(self.update(4,'/start '+code));self.assertEqual(self.settings.read()['owner_id'],123);self.assertEqual(self.bridge.pair_code,'')
  self.bridge.handle_update(self.update(5,'reconstruct D:/x.hdf5',user=456));self.bridge.incoming.emit.assert_not_called()
  self.bridge.handle_update(self.update(6,'hi'));self.assertEqual(self.bridge.incoming.emit.call_count,1)
 def test_duplicate_and_old_messages_do_not_execute(self):
  self.pair();msg=self.update(2,'reconstruct D:/x.hdf5');self.bridge.handle_update(msg);self.bridge.handle_update(msg)
  self.bridge.handle_update(self.update(3,'reconstruct D:/old.hdf5',date=int(time.time())-1000))
  self.assertEqual(self.bridge.incoming.emit.call_count,1)
  restarted=TelegramBridge(self.settings,api=Mock());restarted.incoming=Mock();restarted.handle_update(msg);restarted.incoming.emit.assert_not_called();restarted.stop()
 def test_expired_code_groups_forwarded_messages_and_media_are_rejected(self):
  code=self.bridge.new_pair_code();self.bridge.pair_expires=0;self.bridge.handle_update(self.update(1,'/start '+code));self.assertFalse(self.settings.read().get('owner_id'))
  code=self.bridge.new_pair_code();self.bridge.handle_update(self.update(2,'/start '+code))
  forwarded=self.update(3,'reconstruct D:/x.hdf5');forwarded['message']['forward_origin']={'type':'user'};self.bridge.handle_update(forwarded)
  self.bridge.handle_update(self.update(4,'run',kind='group'));self.bridge.handle_update(self.update(5,''));self.bridge.incoming.emit.assert_not_called()
 def test_stop_blocks_new_dispatch(self):
  self.pair();offset=self.settings.read()['offset'];self.bridge.stop();self.bridge.handle_update(self.update(2,'run'));self.bridge.incoming.emit.assert_not_called();self.assertEqual(self.settings.read()['offset'],offset)
 def test_sender_coalesces_working_and_edits_the_same_reply(self):
  self.settings.update(owner_id=123,chat_id=123);api=Mock();calls=[]
  def call(method,payload,file=None,timeout=None):
   calls.append((method,payload,file));return {'message_id':101}
  api.call.side_effect=call;bridge=TelegramBridge(self.settings,api=api)
  bridge.send_text('Working…','reply');bridge.send_text('Completed: center 1017','reply')
  sender=threading.Thread(target=bridge.send_loop,daemon=True);sender.start()
  until=time.monotonic()+2
  while not calls and time.monotonic()<until:time.sleep(.01)
  self.assertEqual(calls[0][1]['text'],'Completed: center 1017');self.assertEqual(calls[0][0],'sendMessage')
  bridge.send_text('Verified: center 1017','reply');until=time.monotonic()+2
  while len(calls)<2 and time.monotonic()<until:time.sleep(.01)
  self.assertEqual(calls[1][0],'editMessageText');self.assertEqual(calls[1][1]['message_id'],101)
  image=Path(self.tmp.name)/'curve.png';image.write_bytes(b'saved-artifact');bridge.send_image(image);until=time.monotonic()+2
  while len(calls)<3 and time.monotonic()<until:time.sleep(.01)
  self.assertEqual(calls[2][0],'sendPhoto');self.assertEqual(calls[2][2],image);bridge.stop();sender.join(1)
 @unittest.skipUnless(os.name=='nt','Windows DPAPI')
 def test_token_is_encrypted_and_changed_bot_loses_old_owner(self):
  token='123456:abcdefghijklmnopqrstuvwxyz_0123456789';self.settings.configure(token);self.assertEqual(self.settings.token(),token);self.assertNotIn(token,self.settings.path.read_text())
  self.settings.update(owner_id=123);self.settings.configure(token);self.assertEqual(self.settings.read()['owner_id'],123)
  self.settings.configure('234567:abcdefghijklmnopqrstuvwxyz_0123456789');self.assertFalse(self.settings.read().get('owner_id'))
 def test_http_errors_do_not_expose_token(self):
  token='123456:supersecret';error=urllib.error.HTTPError('https://api.telegram.org/bot'+token+'/getMe',401,'Unauthorized',{},io.BytesIO(json.dumps({'description':token+' unauthorized'}).encode()))
  with patch('urllib.request.urlopen',side_effect=error):
   with self.assertRaises(TelegramError) as result:TelegramAPI(token).call('getMe')
  self.assertNotIn(token,str(result.exception));self.assertEqual(result.exception.code,401)

class TelegramDesktopTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.w=ChatWindow(Conversations(self.root/'conversations'),JobStore(self.root/'jobs'),autoload=False,model_first=False);self.w.new_task();self.w.show();self.pump(.1)
  self.control=self.w.telegram;self.bridge=FakeBridge();self.control.bridge=self.bridge;self.control.settings.update(owner_id=123,chat_id=123)
  self.local=self.w.current;self.w.composer.setPlainText('Unsent desktop draft')
  self.remote=self.w.repo.create();self.w.tasks[self.remote['id']]=self.remote;self.control.subscribe(self.remote)
 def tearDown(self):self.w.close();self.pump(.05);self.tmp.cleanup()
 def pump(self,seconds):
  end=time.monotonic()+seconds
  while time.monotonic()<end:self.app.processEvents();time.sleep(.005)
 def send(self,text):self.control.receive({'text':text,'owner_id':123,'message_id':1});self.pump(.05)
 def test_remote_greeting_preserves_local_task_and_draft(self):
  before=copy.deepcopy(self.remote['settings']);self.send('hello..');self.assertIn('MomoBot',self.remote['messages'][-1]['text']);self.assertEqual(self.remote['settings'],before)
  self.assertEqual(self.w.current_id,self.local['id']);self.assertEqual(self.w.composer.toPlainText(),'Unsent desktop draft');self.assertTrue(any('MomoBot' in x[0] for x in self.bridge.texts))
  self.assertEqual(len(self.bridge.stickers),1);self.control.sync();self.assertEqual(len(self.bridge.stickers),1)
  self.send('Hi!');self.assertEqual(len(self.bridge.stickers),2)
 def test_setup_has_a_visible_labeled_token_field_and_working_paste_button(self):
  self.control.bridge=None;self.control.show();self.pump(.05)
  field=self.control.token_input;self.assertTrue(field.isVisible());self.assertGreaterEqual(field.height(),46);self.assertEqual(field.accessibleName(),'Bot token');self.assertEqual(field.echoMode(),QLineEdit.Password)
  clipboard=self.app.clipboard();previous=clipboard.text()
  try:
   clipboard.setText('123456:local_test_token_not_sent_anywhere')
   paste=next(b for b in self.control.dialog.findChildren(QPushButton) if b.text()=='Paste token');QTest.mouseClick(paste,Qt.LeftButton);self.assertEqual(field.text(),'123456:local_test_token_not_sent_anywhere')
  finally:clipboard.setText(previous)
  self.control.dialog.close();self.pump(.05)
 def test_initial_setup_shows_only_token_step_and_help_is_optional(self):
  self.control.bridge=None;self.control.show();self.pump(.05);dialog=self.control.dialog
  self.assertEqual(dialog.page_name,'token');self.assertTrue(dialog.pages['token'].isVisible());self.assertFalse(dialog.pages['pair'].isVisible());self.assertFalse(dialog.pages['connected'].isVisible());self.assertFalse(dialog.help_panel.isVisible())
  QTest.mouseClick(dialog.help_button,Qt.LeftButton);self.assertTrue(dialog.help_panel.isVisible());self.assertEqual(decode_qr(dialog.help_qr.pixmap().toImage()),'https://t.me/BotFather')
  dialog.close();self.pump(.05)
 def test_qr_opens_the_correct_bot_and_start_completes_pairing(self):
  from urllib.parse import urlparse,parse_qs
  self.control.settings.update(owner_id=None,chat_id=None);bridge=TelegramBridge(self.control.settings,api=Mock());bridge.send_text=Mock();self.control.bridge=bridge;bridge.paired.connect(self.control.paired)
  self.control.show();self.control.connected({'username':'MomoBot_test_bot'});self.pump(.05);dialog=self.control.dialog
  self.assertEqual(dialog.page_name,'pair');self.assertFalse(dialog.pages['token'].isVisible());self.assertTrue(dialog.pair_qr.isVisible())
  decoded=decode_qr(dialog.pair_qr.pixmap().toImage());self.assertEqual(urlparse(decoded).path,'/MomoBot_test_bot');code=parse_qs(urlparse(decoded).query)['start'][0];self.assertEqual(code,bridge.pair_code)
  self.assertNotIn('token',decoded.casefold());self.assertTrue(decoded.startswith('https://t.me/'))
  bridge.handle_update({'update_id':1,'message':{'date':int(time.time()),'text':'/start '+code,'chat':{'id':123,'type':'private'},'from':{'id':123,'is_bot':False}}});self.pump(.05)
  self.assertEqual(self.control.settings.read()['owner_id'],123);self.assertEqual(dialog.page_name,'connected');self.assertFalse(dialog.pages['pair'].isVisible());self.assertTrue(dialog.pair_qr.pixmap().isNull());dialog.close();self.pump(.05)
 def test_expired_displayed_qr_refreshes_and_old_start_code_is_rejected(self):
  self.control.settings.update(owner_id=None,chat_id=None);bridge=TelegramBridge(self.control.settings,api=Mock());bridge.send_text=Mock();self.control.bridge=bridge
  self.control.show();self.control.connected({'username':'MomoBot_test_bot'});dialog=self.control.dialog;old=bridge.pair_code;bridge.pair_expires=time.monotonic()-1;dialog.refresh();new=bridge.pair_code
  self.assertNotEqual(old,new);self.assertIn(new,decode_qr(dialog.pair_qr.pixmap().toImage()))
  bridge.handle_update({'update_id':1,'message':{'date':int(time.time()),'text':'/start '+old,'chat':{'id':123,'type':'private'},'from':{'id':123,'is_bot':False}}});self.assertFalse(self.control.settings.read().get('owner_id'));dialog.close();self.pump(.05)
 def test_connection_failure_returns_to_editable_token_step(self):
  self.control.bridge=None;self.control.show();self.control.set_status('Connecting…');dialog=self.control.dialog;self.assertFalse(dialog.connect_button.isEnabled());self.control.set_status('Telegram 401: Unauthorized')
  self.assertEqual(dialog.page_name,'token');self.assertTrue(dialog.connect_button.isEnabled());self.assertTrue(dialog.token_input.isEnabled());self.assertIn('401',dialog.status.text());dialog.close();self.pump(.05)
 def test_non_owner_cannot_even_list_tasks(self):
  self.control.receive({'text':'/tasks','owner_id':999});self.assertEqual(self.bridge.texts,[])
 def test_remote_submission_uses_existing_worker_adapter(self):
  self.remote['settings']['output_root']=str(self.root/'jobs');mark(self.remote,'checkpoint');fake=Mock();fake.running=True;self.w.model_ready=True
  fake.converse.return_value=(Plan('segment',{'image_folder':'D:/images','prompt':'particle'},'Segmenting images.'),{'center_mode':'unchanged','row_scope':'unchanged','accept_defaults':False},{})
  job={'id':'owned','job_dir':str(self.root/'jobs/owned'),'action':'segment'}
  with patch.object(self.w,'model',fake),patch('assistant_lab.chat_window.ROOT',self.root),patch('assistant_lab.chat_window.resolve_source',return_value='D:/images'),patch('assistant_lab.chat_window.inspect_source',return_value={'images':2}),patch('assistant_lab.chat_window.JobStore.submit',return_value=job) as submit:
   self.send('Segment D:/images with particle.');self.pump(.5)
  self.assertEqual(submit.call_args.args[0],'segment');self.assertEqual(submit.call_args.args[1]['image_folder'],'D:/images');self.assertEqual(self.w.current_id,self.local['id']);self.assertEqual(self.w.composer.toPlainText(),'Unsent desktop draft')
 def test_working_is_replaced_by_actual_result(self):
  message(self.remote,'assistant','');entry=self.remote['messages'][-1];activity(self.remote,entry['id'],'Searching center');self.control.sync();key=self.bridge.texts[-1][1];self.assertTrue(self.bridge.texts[-1][0].startswith('Working'))
  entry['text']='Rotation center: 1017 px';finish_activity(self.remote,entry['id']);self.control.sync();self.assertEqual(self.bridge.texts[-1],('Rotation center: 1017 px',key))
 def test_image_query_sends_only_saved_artifact_without_opening_desktop(self):
  folder=self.root/'jobs/search';artifact=folder/'results/center_search/best_input.png';artifact.parent.mkdir(parents=True);artifact.write_bytes(b'local-test-image')
  atomic_json(folder/'job.json',{'id':'search','settings':{}});atomic_json(folder/'job_status.json',{'state':'succeeded','result':{'recommended_center':1017}})
  self.remote['jobs']=[dict(id='search',job_dir=str(folder),action='find_center',reported=True)]
  with patch('assistant_lab.chat_window.QDesktopServices.openUrl') as opened:self.send('/image');self.pump(.2);opened.assert_not_called()
  self.assertEqual(self.bridge.images,[str(artifact)])
 def test_stop_while_model_is_busy_prevents_late_job_submission(self):
  fake=Mock();fake.running=True;self.w.model_ready=True
  def delayed(*args):
   time.sleep(.12);return Plan('reconstruct',{'input_hdf5':'D:/x.hdf5'},'Will reconstruct.'),{'center_mode':'auto','row_scope':'all','accept_defaults':False},{}
  fake.converse.side_effect=delayed
  with patch.object(self.w,'model',fake),patch.object(self.w.store,'submit',side_effect=AssertionError('Cancelled request must not submit')):
   self.control.receive({'text':'Reconstruct D:/x.hdf5','owner_id':123});self.assertTrue(self.w.busy);self.control.receive({'text':'/stop','owner_id':123});self.pump(.35)
  self.assertFalse(self.remote['run_requested']);self.assertTrue(self.remote['cancel_requested']);self.assertFalse(self.remote['jobs']);self.assertTrue(any('cancelled' in m['text'] for m in self.remote['messages']))
 def test_busy_message_is_not_queued_as_a_future_compute_request(self):
  self.w.busy=True;before=len(self.remote['messages']);self.send('Reconstruct D:/x.hdf5');self.w.busy=False
  self.assertEqual(len(self.remote['messages']),before);self.assertIn('has not run',self.bridge.texts[-1][0])
 def test_new_and_switch_do_not_change_visible_desktop(self):
  self.send('/new');identity=self.control.settings.read()['task_id'];self.assertNotEqual(identity,self.remote['id']);self.send('/use '+self.remote['id']);self.assertEqual(self.control.task()['id'],self.remote['id']);self.assertEqual(self.w.current_id,self.local['id'])

if __name__=='__main__':unittest.main()
