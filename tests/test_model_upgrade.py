import os,sys,json,tempfile,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch,Mock
from assistant_lab.path_rules import normalize_path,path_key,extract_paths,ground_path_updates
from assistant_lab.chat_model import ChatModel
from assistant_lab.chat_flow import bind_paths,apply_defaults,execution_intent
from assistant_lab.conversations import new_task,choose_kind,apply_response,accept_source,PATHS
from assistant_lab.task_recovery import recover_task
from assistant_lab.llm import LocalModel
from assistant_lab.config import DEFAULTS,MODEL_PROFILES

COMMAND='can you recon this file:///D:/1_Datasets/2_Tomography/hdf5_collection/NMC622_Rod5.hdf5?'
EXPECTED='D:/1_Datasets/2_Tomography/hdf5_collection/NMC622_Rod5.hdf5'

def task():
 t=new_task();choose_kind(t,'reconstruct');t['settings'].update(input_hdf5='D:/old.hdf5',center=1017.,gpu=0);t['center_mode']='known';return t

def packet(updates,action='reconstruct',mode='known'):
 return {'plan':{'action':action,'updates':[{'field':k,'value':str(v)} for k,v in updates.items()],'message':'I will check the requested file.'},'center_mode':mode,'row_scope':'unchanged','accept_defaults':False}

def interpret(command,t,response):
 with tempfile.TemporaryDirectory() as tmp,patch('assistant_lab.chat_model.ROOT',Path(tmp)),patch('assistant_lab.chat_model.post_json',side_effect=[{'prompt':'test prompt'},{'content':json.dumps(response)}]):return ChatModel().converse(command,t)

class PathGroundingTests(unittest.TestCase):
 def test_uri_native_wsl_and_quoted_paths_are_canonical(self):
  self.assertEqual(normalize_path('file:///D:/data%20folder/%E7%B2%92%E5%AD%90.hdf5'),'D:/data folder/粒子.hdf5')
  self.assertEqual(normalize_path('/mnt/d/data/a.hdf5'),'D:/data/a.hdf5');self.assertEqual(normalize_path('file://localhost/D:/data/a.hdf5'),'D:/data/a.hdf5')
  self.assertEqual(normalize_path('file://server/share/a.hdf5'),'//server/share/a.hdf5')
  self.assertEqual(extract_paths(COMMAND),[EXPECTED]);self.assertEqual(extract_paths('Use "D:\\data folder\\a.hdf5".'),['D:/data folder/a.hdf5'])
  self.assertEqual(extract_paths('[data](file:///D:/data/a.hdf5)'),['D:/data/a.hdf5'])
 def test_substrings_do_not_authorize_different_files(self):
  with self.assertRaises(ValueError):ground_path_updates([{'field':'input_hdf5','value':'D:/data/a.hdf5'}],'Reconstruct D:/data/a.hdf5.backup',{},PATHS)
 def test_reported_failure_packet_recovers_exact_source_without_old_coordinates(self):
  t=task();p,c,meta=interpret(COMMAND,t,packet({'center':'1017.0','method':'fourierrec','gpu':'1','start_row':'1022','end_row':'1027','output_root':'D:\\\\BL62_Assistant_Chat\\\\outputs\\\\jobs'}))
  self.assertNotIn('output_root',p.updates);self.assertNotIn('center',p.updates);self.assertNotIn('gpu',p.updates);self.assertNotIn('start_row',p.updates);self.assertEqual(c['center_mode'],'unchanged')
  bind_paths(t,p,COMMAND);self.assertEqual(p.updates['input_hdf5'],EXPECTED);apply_response(t,p,c['center_mode']);self.assertEqual(t['settings']['center'],0);self.assertEqual(t['settings']['gpu'],0)
  accept_source(t,'input_hdf5',EXPECTED,{'rows':2048,'width':2048,'projections':1800});apply_defaults(t);self.assertEqual((t['settings']['start_row'],t['settings']['end_row']),(0,2048))
 def test_model_file_url_is_converted_before_opening(self):
  p,c,_=interpret(COMMAND,task(),packet({'input_hdf5':'file:///'+EXPECTED}));self.assertEqual(p.updates['input_hdf5'],EXPECTED)
 def test_all_slices_does_not_take_path_digits_as_explicit_rows(self):
  text='Find center using particle then reconstruct all slices for '+EXPECTED
  raw=packet({'input_hdf5':EXPECTED,'prompt':'particle','start_row':'0','end_row':'0'},action='analyze',mode='auto');raw['row_scope']='all'
  p,c,_=interpret(text,task(),raw);self.assertNotIn('start_row',p.updates);self.assertNotIn('end_row',p.updates);self.assertEqual(c['row_scope'],'all')
 def test_parameter_names_inside_quoted_paths_are_not_commands(self):
  from assistant_lab.answer_bindings import explicit_answer
  bindings,_=explicit_answer('Reconstruct "D:/GPU 1/center 999/row 3/a.hdf5"',task());self.assertNotIn('center',bindings);self.assertNotIn('gpu',bindings);self.assertNotIn('start_row',bindings)
 def test_explicit_coordinates_and_gpu_override_model_guesses(self):
  text=COMMAND+' Use center 1028.5, start row 7 end row 9 on GPU 0.';t=task();t['state']='completed'
  p,c,_=interpret(text,t,packet({'input_hdf5':EXPECTED,'center':'999','gpu':'1','start_row':'1022','end_row':'1027'}))
  self.assertEqual(p.action,'reconstruct');self.assertEqual(p.updates['center'],1028.5);self.assertEqual(p.updates['gpu'],0);self.assertEqual((p.updates['start_row'],p.updates['end_row']),(7,9));self.assertEqual(c['center_mode'],'known')
 def test_unchanged_path_does_not_need_repeating_in_followup(self):
  t=task();p,c,_=interpret('Reconstruct the current data.',t,packet({'input_hdf5':'D:\\old.hdf5','center':'1017'}));self.assertEqual(p.updates,{});apply_response(t,p,c['center_mode']);self.assertEqual(t['settings']['center'],1017)
 def test_invented_source_path_is_still_rejected(self):
  with self.assertRaises(ValueError):interpret(COMMAND,task(),packet({'input_hdf5':'D:/some-other-file.hdf5'}))
 def test_recon_is_an_execution_request_but_explanations_are_not(self):
  self.assertTrue(execution_intent(COMMAND));self.assertFalse(execution_intent('How can I recon this data?'));self.assertFalse(execution_intent('Explain how to reconstruct it, do not run.'))

class RecoveryAndGpuTests(unittest.TestCase):
 def test_failed_legacy_url_cannot_restore_another_datasets_center(self):
  t=task();t['settings']['input_hdf5']='file:///'+EXPECTED;t['messages']=[{'role':'user','text':COMMAND}]
  recover_task(t,[{'recommended_center':1017,'source':'D:/old.hdf5'}]);self.assertEqual(t['settings']['input_hdf5'],EXPECTED);self.assertEqual(t['settings']['center'],0);self.assertIsNone(t['center_mode']);self.assertFalse(t['run_requested'])
 def test_legacy_url_preserves_an_explicitly_requested_center(self):
  t=task();t['settings']['input_hdf5']='file:///'+EXPECTED;t['messages']=[{'role':'user','text':COMMAND+' center 1001.5'}];recover_task(t,[]);self.assertEqual(t['settings']['center'],1001.5)
 def test_result_restore_is_source_specific_and_does_not_override_manual_center(self):
  t=task();t['settings']['center']=0;recover_task(t,[{'source':'D:/different.hdf5','recommended_center':777},{'source':'file:///D:/old.hdf5','recommended_center':888}]);self.assertEqual(t['settings']['center'],888)
  t['settings']['center']=999;recover_task(t,[{'source':'D:/old.hdf5','recommended_center':888}]);self.assertEqual(t['settings']['center'],999)
 def test_launch_environment_isolated_to_gpu1_and_scientific_defaults_gpu0(self):
  self.assertEqual(DEFAULTS['gpu'],0);self.assertEqual(MODEL_PROFILES['primary']['mode'],'GPU 1')
  original=os.environ.get('CUDA_VISIBLE_DEVICES')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);runtime=root/'runtime/cuda';runtime.mkdir(parents=True);(runtime/'llama-server.exe').write_bytes(b'fake');model=root/'test.gguf';model.write_bytes(b'fake')
   process=Mock();process.poll.return_value=None
   with patch('assistant_lab.llm.ROOT',root),patch('assistant_lab.llm.RUNTIME_ROOT',root/'runtime'),patch('assistant_lab.llm.subprocess.Popen',return_value=process) as popen:
    local=LocalModel();local.start('GPU 1',context=8192,model_path=model);env=popen.call_args.kwargs['env'];args=popen.call_args.args[0]
    self.assertEqual(env['CUDA_VISIBLE_DEVICES'],'1');self.assertEqual(env['CUDA_DEVICE_ORDER'],'PCI_BUS_ID');self.assertIn('8192',args);self.assertIn('off',args);self.assertEqual(os.environ.get('CUDA_VISIBLE_DEVICES'),original);local.stop()

if __name__=='__main__':unittest.main()
