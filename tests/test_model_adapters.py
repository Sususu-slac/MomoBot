import os,sys,json,tempfile,unittest,copy
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from assistant_lab.chat_model import ChatModel,CHAT_SCHEMA
from assistant_lab.request_limits import unsupported_request
from assistant_lab.conversations import new_task,choose_kind,Conversations
from assistant_lab.jobs import JobStore
from assistant_lab.chat_window import ChatWindow
from assistant_lab.config import MODEL_PROFILES
from PySide6.QtWidgets import QApplication

class AdapterTests(unittest.TestCase):
 def test_native_chat_uses_selected_template_and_never_returns_reasoning(self):
  model=ChatModel();model.adapter='chat';model.template_kwargs={'enable_thinking':False};model.max_output_tokens=768
  response={'choices':[{'message':{'content':'{"ok":true}','reasoning_content':'private reasoning'},'finish_reason':'stop'}]}
  with patch('assistant_lab.chat_model.post_json',return_value=response) as post:
   actual=model.structured_reply([{'role':'system','content':'Return a plan'},{'role':'user','content':'Hello'}])
  payload=post.call_args.args[1];self.assertIn('/v1/chat/completions',post.call_args.args[0]);self.assertEqual(payload['max_tokens'],768)
  self.assertEqual(payload['chat_template_kwargs'],{'enable_thinking':False});self.assertEqual(actual['content'],'{"ok":true}')
  self.assertNotIn('private reasoning',json.dumps(actual));self.assertEqual(payload['response_format']['json_schema']['schema'],CHAT_SCHEMA)
 def test_legacy_completion_adapter_retained(self):
  model=ChatModel()
  with patch('assistant_lab.chat_model.post_json',side_effect=[{'prompt':'rendered'},{'content':'{}'}]) as post:
   self.assertEqual(model.structured_reply([{'role':'user','content':'Hello'}])['content'],'{}')
  self.assertTrue(post.call_args_list[0].args[0].endswith('/apply-template'));self.assertEqual(post.call_args_list[1].args[1]['n_predict'],512)
 def test_unsupported_actions_cannot_reach_the_model(self):
  for command in ['Delete all my original pictures permanently.','Automatically score and optimize the laminography tilt angle for me.','自动优化倾斜角','删除所有原始图片']:
   with self.subTest(command=command),patch('assistant_lab.chat_model.post_json',side_effect=AssertionError('Must not call LLM')):
    plan,control,meta=ChatModel().converse(command,new_task());self.assertEqual(plan.action,'clarify');self.assertEqual(plan.updates,{});self.assertTrue(meta['unsupported_capability'])
 def test_supported_requests_and_negative_deletion_constraints_are_not_blocked(self):
  for command in ['Automatically find the rotation center with fixed lamino angle 20.','Generate angle trial reconstructions automatically so I can choose.','Segment images, do not delete the originals.','Reconstruct data and remove stripes.','自动寻找旋转中心，使用倾斜角20度。','分割图片，不要删除原始图片。']:
   with self.subTest(command=command):self.assertIsNone(unsupported_request(command))
 def test_explicit_geometry_replaces_inherited_mode_even_when_model_omits_it(self):
  from assistant_lab.answer_bindings import explicit_answer
  task=new_task();choose_kind(task,'reconstruct');task['settings']['geometry']='laminography'
  for command,expected in [('Reconstruct using tomography.','tomography'),('Use tomo.','tomography'),('Use laminography.','laminography'),('Reconstruct with lamino.','laminography')]:
   self.assertEqual(explicit_answer(command,task)[0]['geometry'],expected)
  self.assertNotIn('geometry',explicit_answer('Reconstruct D:/tomography/data.h5',task)[0])
  self.assertNotIn('geometry',explicit_answer('Compare tomography and laminography.',task)[0])
  self.assertNotIn('geometry',explicit_answer('Do not use laminography.',task)[0])
  self.assertEqual(explicit_answer('Use tomography, not laminography.',task)[0]['geometry'],'tomography')
  packet={'plan':{'action':'reconstruct','updates':[],'message':'Use tomography.'},'center_mode':'known','row_scope':'unchanged','accept_defaults':False}
  with tempfile.TemporaryDirectory() as tmp,patch('assistant_lab.chat_model.STATE_ROOT',Path(tmp)),patch.object(ChatModel,'structured_reply',return_value={'content':json.dumps(packet)}):
   plan,_,meta=ChatModel().converse('Reconstruct using tomography.',task)
  self.assertEqual(plan.updates['geometry'],'tomography');self.assertIn('Verified explicit geometry',meta['normalizations'])
 def test_explicit_binning_factor_overrides_model_exponent(self):
  from assistant_lab.answer_bindings import explicit_answer
  for factor,exponent in [(1,0),(2,1),(4,2),(8,3)]:
   for text in [f'Reconstruct with {factor}x{factor} binning.',f'Binning {factor}×{factor}',f'{factor}×{factor}合并']:
    task=new_task();choose_kind(task,'reconstruct')
    self.assertEqual(explicit_answer(text,task)[0]['binning'],exponent)
  task=new_task();choose_kind(task,'reconstruct')
  self.assertNotIn('binning',explicit_answer('Image dimensions 8x8; use D:/8x8_binning/input.h5',task)[0])
  packet={'plan':{'action':'reconstruct','updates':[{'field':'binning','value':'2'}],'message':'Run reconstruction.'},'center_mode':'unchanged','row_scope':'unchanged','accept_defaults':False}
  with tempfile.TemporaryDirectory() as tmp,patch('assistant_lab.chat_model.STATE_ROOT',Path(tmp)),patch.object(ChatModel,'structured_reply',return_value={'content':json.dumps(packet)}):
   plan,_,meta=ChatModel().converse('Reconstruct using 8x8 binning.',task)
  self.assertEqual(plan.updates['binning'],3);self.assertIn('Verified explicit binning',meta['normalizations'])
 def test_literal_middle_trial_slice_remains_optional_not_a_numeric_word(self):
  task=new_task();choose_kind(task,'try_angle');task['settings']['center']=1028.5
  packet={'plan':{'action':'try_angle','updates':[{'field':'trial_row','value':'middle'}],'message':'Prepare one middle slice.'},'center_mode':'unchanged','row_scope':'unchanged','accept_defaults':False}
  with tempfile.TemporaryDirectory() as tmp,patch('assistant_lab.chat_model.STATE_ROOT',Path(tmp)),patch.object(ChatModel,'structured_reply',return_value={'content':json.dumps(packet)}):
   plan,_,_=ChatModel().converse('Generate angle trials on one middle slice.',task)
  self.assertIsNone(plan.updates['trial_row'])

class ModelPickerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
  with patch('assistant_lab.chat_window.load_preferences',return_value={}):self.window=ChatWindow(Conversations(root/'conversations'),JobStore(root/'jobs'),autoload=False)
 def tearDown(self):self.window.close();self.app.processEvents();self.tmp.cleanup()
 def test_switches_and_persists_available_models(self):
  self.assertEqual(list(MODEL_PROFILES),['gemma4'])
  for key,profile in MODEL_PROFILES.items():
   with patch('assistant_lab.chat_window.QInputDialog.getItem',return_value=(profile['label'],True)),patch('assistant_lab.chat_window.Path.is_file',return_value=True),patch('assistant_lab.chat_window.save_preferences') as save,patch.object(self.window,'load_model') as load:
    self.window.select_language_model();self.assertEqual(self.window.model_profile,key);self.assertEqual(save.call_args.args[0]['model_profile'],key);load.assert_called_once_with(restart=True)
 def test_missing_model_does_not_stop_or_change_the_active_choice(self):
  previous=self.window.model_profile;profile=next(iter(MODEL_PROFILES.values()))
  with patch('assistant_lab.chat_window.QInputDialog.getItem',return_value=(profile['label'],True)),patch('assistant_lab.chat_window.Path.is_file',return_value=False),patch('assistant_lab.chat_window.QMessageBox.information'),patch.object(self.window,'load_model') as load,patch('assistant_lab.chat_window.save_preferences') as save:
   self.window.select_language_model();self.assertEqual(self.window.model_profile,previous);load.assert_not_called();save.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
