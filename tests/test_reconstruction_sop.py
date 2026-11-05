import os,sys,json,tempfile,time,copy,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen';sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import h5py,numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations
from assistant_lab.jobs import JobStore,atomic_json
from assistant_lab.trial_candidates import catalogue,selection
from assistant_lab.reconstruction_sop import fingerprint,estimate

class SOPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);self.source=self.r/'first.h5';self.other=self.r/'second.h5'
  for p in [self.source,self.other]:
   with h5py.File(p,'w') as h:
    h['exchange/data']=np.ones((7,32,64),np.uint16);h['exchange/data_white']=np.ones((1,32,64),np.uint16)*2;h['exchange/data_dark']=np.zeros((1,32,64),np.uint16);h['exchange/theta']=np.linspace(0,360,7,dtype=np.float32)
  self.w=ChatWindow(Conversations(self.r/'conversations'),JobStore(self.r/'jobs'),autoload=False,model_first=False);self.t=self.w.current;self.t['settings']['output_root']=str(self.r/'jobs');self.calls=[]
  def submit(store,action,settings,plan=None):
   folder=store.root/str(len(self.calls));folder.mkdir(parents=True);job=dict(id=folder.name,action=action,job_dir=str(folder));self.calls.append((job,copy.deepcopy(settings)));atomic_json(folder/'job.json',{**job,'settings':settings});atomic_json(folder/'job_status.json',dict(state='queued'));return job
  self.submitpatch=patch.object(JobStore,'submit',autospec=True,side_effect=submit);self.submitpatch.start()
 def pump(self):
  end=time.monotonic()+4
  while time.monotonic()<end:
   self.app.processEvents();time.sleep(.005)
   if not self.w.busy:break
  for _ in range(15):self.app.processEvents();time.sleep(.005)
 def send(self,text):self.w.submit_text(self.t,text);self.pump()
 def tearDown(self):self.pump();self.w.close();self.app.processEvents();self.submitpatch.stop();self.tmp.cleanup()
 def prepare(self,command=None):self.send(command or f'Reconstruct "{self.source}" using tomography, center 31.5, start row 8 end row 12, 2x2 binning.')
 def complete(self,result,stage=None):
  job=self.t['jobs'][-1];atomic_json(Path(job['job_dir'])/'job_status.json',dict(state='succeeded',result=result,output=str(Path(job['job_dir'])/'results'),elapsed_seconds=4));self.w.poll();self.pump()
 def test_metadata_first_then_geometry_reason_then_method(self):
  self.send(str(self.source));self.assertEqual(self.t['sop']['phase'],'geometry');self.assertFalse(self.calls)
  messages='\n'.join(m['text'] for m in self.t['messages']);self.assertIn('Projections: 7',messages);self.assertIn('uint16',messages);self.assertIn('Theta',messages);self.assertIn('both',messages)
  self.send('tomo');self.assertEqual(self.t['sop']['phase'],'mode');self.assertFalse(self.calls)
 def test_clear_request_requires_only_one_confirmation(self):
  self.prepare();self.assertEqual(self.t['sop']['phase'],'confirm');self.assertFalse(self.calls);self.assertIn('Estimated time',self.t['messages'][-1]['text'])
  self.send('yes');self.assertEqual(len(self.calls),1);job,s=self.calls[0];self.assertEqual(job['action'],'reconstruct');self.assertEqual(s['center'],31.5);self.assertEqual(s['geometry'],'tomography');self.assertEqual(s['binning'],1)
 def test_lamino_without_angle_must_ask_and_never_guess(self):
  self.prepare(f'Reconstruct "{self.source}" using laminography, center 31.5.')
  self.assertEqual(self.t['sop']['phase'],'angle');self.assertFalse(self.calls)
  self.send('27.5');self.assertEqual(self.t['sop']['phase'],'confirm');self.send('confirm reconstruction');self.assertEqual(self.calls[0][1]['lamino_angle'],27.5)
 def test_complete_automatic_text_request_confirms_once_then_analyze(self):
  self.prepare(f'Automatically reconstruct "{self.source}" using tomography, text prompt particle, start row 8 end row 12.')
  self.assertEqual(self.t['sop']['phase'],'confirm');self.assertFalse(self.calls);self.assertTrue(self.t['sop']['automatic_full'])
  self.send('confirm reconstruction');self.assertEqual(self.calls[0][0]['action'],'analyze');self.assertEqual(self.calls[0][1]['prompt'],'particle')
 def test_auto_missing_target_is_asked_not_silently_particle(self):
  self.prepare(f'Automatically reconstruct "{self.source}" using tomography.')
  self.assertEqual(self.t['sop']['phase'],'target');self.assertFalse(self.calls);self.send('particle');self.assertEqual(self.t['sop']['phase'],'confirm')
 def test_manual_opens_numbered_folder_then_selection_only_reviews(self):
  self.prepare(f'Reconstruct "{self.source}" using tomography, manual, start row 8 end row 12.')
  self.assertEqual(self.t['sop']['phase'],'trial_offer');self.send('generate candidates');self.assertEqual(self.calls[0][0]['action'],'try_center')
  files=[]
  for c in [30.,31.,32.]:
   p=self.r/f'recon_slice0016_center{c:.2f}.tiff';Image.fromarray(np.arange(256,dtype=np.float32).reshape(16,16)).save(p);files.append(str(p))
  items=catalogue(files)
  with patch.object(self.w.sop,'open_folder',return_value=True) as opened:self.complete(dict(candidates=3,files=files,folder=str(self.r),candidate_catalogue=items))
  opened.assert_called_once();self.assertEqual(self.t['sop']['phase'],'choose');self.send('第3张');self.assertEqual(self.t['settings']['center'],32);self.assertEqual(self.t['sop']['phase'],'confirm');self.assertEqual(len(self.calls),1)
  self.send('确认重建');self.assertEqual(len(self.calls),2);self.assertEqual(self.calls[-1][0]['action'],'reconstruct')
 def test_new_input_clears_center_geometry_example_and_confirmation(self):
  self.prepare();self.t['settings']['instance_reference']={'image':'old'};self.send(str(self.other))
  self.assertEqual(self.t['sop']['phase'],'geometry');self.assertEqual(self.t['settings']['center'],0);self.assertEqual(self.t['settings']['instance_reference'],{});self.assertFalse(self.calls)
 def test_in_place_input_change_invalidates_confirmation_and_reloads(self):
  self.prepare()
  with h5py.File(self.source,'a') as h:h.attrs['changed']='yes'
  self.send('yes');self.assertFalse(self.calls);self.assertEqual(self.t['sop']['phase'],'geometry')
 def test_cancel_then_yes_does_not_start(self):
  self.prepare();self.send('cancel');self.send('yes');self.assertFalse(self.calls);self.assertEqual(self.t['sop']['phase'],'paused')
 def test_direct_run_button_cannot_bypass_geometry_or_confirmation(self):
  self.send(str(self.source));self.w.start_task(self.t);self.assertFalse(self.calls)
 def test_instance_reference_and_mask_are_validated_and_forwarded(self):
  self.prepare(f'Automatically reconstruct "{self.source}" using tomography.')
  image=self.r/'example.png';mask=self.r/'mask.png';Image.fromarray(np.arange(256,dtype=np.uint8).reshape(16,16)).save(image);Image.fromarray(np.pad(np.ones((8,8),np.uint8)*255,4)).save(mask)
  with patch('assistant_lab.reconstruction_sop.STATE_ROOT',self.r/'state'):
   self.send(f'instance image "{image}" mask "{mask}"')
  self.assertEqual(self.t['sop']['phase'],'confirm');self.send('yes');s=self.calls[0][1];self.assertEqual(s['prompt_mode'],'instance');self.assertTrue(Path(s['instance_reference']['mask']).is_file())
 def test_folder_selection_is_one_based_and_does_not_auto_batch(self):
  self.w.sop.bootstrap(self.t);self.send(str(self.r));self.assertEqual(self.t['sop']['phase'],'file');self.assertFalse(self.calls);self.send('2');self.assertEqual(Path(self.t['settings']['input_hdf5']),self.other)
 def test_invalid_source_reports_error_without_jobs(self):
  self.send(str(self.r/'missing.h5'));self.assertFalse(self.calls);self.assertEqual(self.t['sop']['phase'],'path')
 def test_pilot_completes_restores_full_rows_and_estimates(self):
  self.prepare();self.send('measure time');self.assertEqual(self.t['jobs'][-1]['sop_stage'],'pilot')
  folder=Path(self.t['jobs'][-1]['job_dir'])/'results/reconstruction';folder.mkdir(parents=True);atomic_json(folder/'run_metadata.json',dict(elapsed_seconds=10))
  self.complete(dict(slices=4,folder=str(folder)));self.assertEqual([self.t['settings']['start_row'],self.t['settings']['end_row']],[8,12]);self.assertEqual(self.t['sop']['phase'],'confirm');self.assertIn('extrapolated',estimate(self.t))

class SelectionTests(unittest.TestCase):
 def test_index_filename_decimal_and_ambiguity(self):
  items=[dict(index=i,value=float(100+i),file=f'/results/recon_center{100+i}.tiff') for i in range(1,5)]
  for text in ['第3张','第三张','candidate 3','3rd','recon_center103.tiff','103','center 103']:
   self.assertEqual(selection(text,items,2048)[0],103,text)
  small=[dict(index=1,value=2.,file='a.tiff'),dict(index=2,value=3.,file='b.tiff')]
  self.assertIsNone(selection('2',small,64)[0]);self.assertIsNotNone(selection('the sharpest one',items,2048)[1])
 def test_catalogue_uses_numeric_center_sort_not_lexical_filename_order(self):
  items=catalogue(['recon_center10.00.tiff','recon_center2.00.tiff','recon_center9.00.tiff']);self.assertEqual([x['value'] for x in items],[2.,9.,10.])
if __name__=='__main__':unittest.main(verbosity=2)
