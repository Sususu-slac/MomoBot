import os,sys,tempfile,time,unittest,threading,json
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from PIL import Image
from assistant_lab.visual_assets import APP_ICON,STICKERS
from assistant_lab.quick_replies import quick_reply,greeting_sticker
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations
from assistant_lab.jobs import JobStore
from assistant_lab.telegram_bridge import TelegramBridge,TelegramSettings,TelegramAPI

class MascotAssets(unittest.TestCase):
 def test_icon_has_windows_sizes_and_sticker_has_transparency(self):
  with Image.open(APP_ICON) as icon:self.assertTrue({(16,16),(32,32),(48,48),(128,128),(256,256)}.issubset(icon.ico.sizes()))
  for kind in ('chat','telegram'):
   path=STICKERS['kitten_hi'][kind]
   with Image.open(path) as image:self.assertEqual(image.mode,'RGBA');self.assertEqual(image.getextrema()[-1],(0,255))
  with Image.open(STICKERS['kitten_hi']['telegram']) as image:self.assertEqual(image.size,(512,512))
  self.assertLess(STICKERS['kitten_hi']['telegram'].stat().st_size,512*1024)
 def test_only_whole_greetings_trigger_stickers(self):
  for text in ('hi','Hello..','hey','你好','Hi, MomoBot!'):self.assertEqual(greeting_sticker(text),'kitten_hi');self.assertIsNotNone(quick_reply(text))
  for text in ('thanks','particle','yes','Hello, reconstruct D:/data.hdf5','你好，分割数据'):self.assertIsNone(greeting_sticker(text))
 def test_upload_uses_the_telegram_sticker_field(self):
  response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=json.dumps({'ok':True,'result':{'message_id':1}}).encode()
  with patch('urllib.request.urlopen',return_value=response) as request:TelegramAPI('local-test-token').call('sendSticker',{'chat_id':123},file=STICKERS['kitten_hi']['telegram'])
  body=request.call_args.args[0].data;self.assertIn(b'name="sticker";',body);self.assertNotIn(b'name="document";',body)
 def test_repeated_greetings_use_cached_telegram_file_without_duplicate_sends(self):
  with tempfile.TemporaryDirectory() as tmp:
   settings=TelegramSettings(Path(tmp)/'telegram.json');settings.update(owner_id=123,chat_id=123);api=Mock();calls=[]
   def call(method,payload,file=None,timeout=None):calls.append((method,dict(payload),file));return {'message_id':1,'sticker':{'file_id':'cached-sticker'}}
   api.call.side_effect=call;bridge=TelegramBridge(settings,api=api);path=STICKERS['kitten_hi']['telegram'];bridge.send_sticker(path,'greeting1');bridge.send_sticker(path,'greeting1');bridge.send_sticker(path,'greeting2')
   worker=threading.Thread(target=bridge.send_loop,daemon=True);worker.start();deadline=time.monotonic()+4
   while len(calls)<2 and time.monotonic()<deadline:time.sleep(.01)
   bridge.stop();worker.join(1);self.assertEqual(len(calls),2);self.assertEqual(calls[0][0],'sendSticker');self.assertEqual(calls[0][2],path);self.assertIsNone(calls[1][2]);self.assertEqual(calls[1][1]['sticker'],'cached-sticker')

class MascotChat(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_greeting_replies_render_and_persist_without_inference_or_jobs(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);repo=Conversations(root/'conversations');window=ChatWindow(repo,JobStore(root/'jobs'),autoload=False);window.show();self.app.processEvents();task=window.current
   fake=Mock();fake.running=True;window.model_ready=True
   with patch.object(window,'model',fake),patch.object(window.store,'submit',side_effect=AssertionError('Greeting must not launch science')):
    for text in ('Hi','hello..','你好'):
     window.composer.setPlainText(text);window.send();self.app.processEvents();entry=task['messages'][-1];self.assertEqual(entry['sticker'],'kitten_hi');self.assertTrue(window.views[entry['id']].sticker.isVisible());self.assertFalse(window.views[entry['id']].sticker.pixmap().isNull())
    fake.converse.assert_not_called()
   saved=repo.all()[0];self.assertEqual(sum(m.get('sticker')=='kitten_hi' for m in saved['messages']),3);self.assertFalse(saved['jobs']);window.close();self.app.processEvents()
 def test_hi_is_immediate_while_loading_and_does_not_uncancel_a_task(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);window=ChatWindow(Conversations(root/'conversations'),JobStore(root/'jobs'),autoload=False);window.show();window.busy=True;task=window.current;task['cancel_requested']=True
   window.composer.setPlainText('Hi');self.assertTrue(window.send_btn.isEnabled());window.send();self.app.processEvents();self.assertEqual(task['messages'][-1]['sticker'],'kitten_hi');self.assertTrue(task['cancel_requested']);self.assertFalse(task['jobs']);window.busy=False;window.close();self.app.processEvents()

if __name__=='__main__':unittest.main()
