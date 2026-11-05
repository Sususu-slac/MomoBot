import copy,json,tempfile,time,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import h5py,numpy as np
from PySide6.QtWidgets import QApplication
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations,choose_kind
from assistant_lab.jobs import JobStore,atomic_json
from assistant_lab.reconstruction_understanding import parse_turn
from assistant_lab.chat_model import ChatModel

def turn(intent='configure',updates=None,**kw):
 return dict(intent=intent,operation='unchanged',mode='unchanged',row_scope='unchanged',updates=updates or {},selection='',query='none',message='Understood.',**kw) if not kw else {**turn(intent,updates),**kw}
def packet(intent='configure',updates=None,**kw):
 t=turn(intent,updates,**kw);t['updates']=[{'field':k,'value':str(v)} for k,v in (updates or {}).items()];return t

class ModelFirstReconstructionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'sample.h5'
  with h5py.File(self.source,'w') as h:
   h['exchange/data']=np.ones((7,32,1616),np.uint16);h['exchange/data_white']=np.ones((1,32,1616),np.uint16)*2;h['exchange/data_dark']=np.zeros((1,32,1616),np.uint16);h['exchange/theta']=np.linspace(0,360,7,dtype=np.float32)
  self.w=ChatWindow(Conversations(self.root/'conversations'),JobStore(self.root/'jobs'),autoload=False);self.w.new_task();self.t=self.w.current
  self.w.model=Mock();self.w.model.running=True;self.w.model_ready=True
  self.w.model.understand_reconstruction.return_value=(turn(),{'model_called':True,'seconds':.1})
  self.jobs=[]
  def submit(store,action,settings,plan=None):
   folder=store.root/str(len(self.jobs));folder.mkdir(parents=True);j=dict(id=folder.name,job_dir=str(folder),action=action);self.jobs.append((j,copy.deepcopy(settings)));atomic_json(folder/'job.json',{**j,'settings':settings});atomic_json(folder/'job_status.json',{'state':'queued'});return j
  self.jobpatch=patch.object(JobStore,'submit',autospec=True,side_effect=submit);self.jobpatch.start()
 def pump(self):
  end=time.monotonic()+5
  while time.monotonic()<end:
   self.app.processEvents();time.sleep(.005)
   if not self.w.busy and not self.w.threads:
    for _ in range(30):self.app.processEvents();time.sleep(.005)
    if not self.w.busy:break
 def seed(self,phase='trial_offer'):
  choose_kind(self.t,'reconstruct');s=self.t['settings'];s.update(input_hdf5=str(self.source),output_root=str(self.root/'jobs'),center=807.5,start_row=0,end_row=32,trial_width=10.,trial_step=1.)
  self.t['metadata']={'rows':32,'width':1616,'projections':7};self.t['done']=['input_hdf5','rows'];self.w.sop.bootstrap(self.t);p=self.t['sop'];st=self.source.stat();p.update(phase=phase,mode='manual',source=str(self.source),source_stat=[st.st_size,st.st_mtime_ns],geometry_confirmed=True,center_valid=False,trial_kind='center',overview_shown=True,full_requested=True)
 def send(self,text,t):
  self.w.model.understand_reconstruction.return_value=(t,{'model_called':True,'seconds':.1});self.w.submit_text(self.t,text);self.pump()
 def tearDown(self):
  self.pump();self.t['state']='draft';self.t['jobs']=[];self.w.close();self.app.processEvents();self.jobpatch.stop();self.tmp.cleanup()
 def test_new_hdf5_folder_goes_to_model_before_metadata_rules(self):
  self.send(f'"{self.root}"',turn('request',operation='inspect'));self.assertEqual(self.w.model.understand_reconstruction.call_count,1);self.assertEqual(self.t['metadata']['width'],1616);self.assertFalse(self.jobs)
 def test_center_and_geometry_requests_route_to_model_on_new_task(self):
  for text in ('find center','find the COR center','找中心','generate lamino angle trials'):
   self.assertTrue(self.w._is_reconstruction_message(self.t,text),text)
 def test_busy_status_does_not_cancel_or_apply_pending_parameters(self):
  self.seed();self.w.busy=True;self.w.submit_text(self.t,'status');self.assertFalse(self.t.get('cancel_requested',False));self.assertEqual(self.t['settings']['trial_width'],10);self.w.busy=False
 def test_busy_status_cannot_undo_a_cancellation(self):
  self.seed();self.w.busy=True;self.t['cancel_requested']=True;self.w.submit_text(self.t,'status');self.assertTrue(self.t['cancel_requested']);self.w.busy=False
 def test_default_router_calls_model_before_any_range_rules(self):
  self.seed();entered=threading.Event();release=threading.Event()
  def understand(*args):entered.set();release.wait(3);return turn(updates={'center':807.5,'trial_width':50.,'trial_step':1.}),{'model_called':True}
  self.w.model.understand_reconstruction.side_effect=understand
  with patch.object(self.w.sop,'handle',side_effect=AssertionError('The rule parser must not run first')):
   self.w.submit_text(self.t,'please 807.5 ± 50 px, step 1');self.assertTrue(entered.wait(1));self.assertEqual(self.t['settings']['trial_width'],10);release.set();self.pump()
  self.assertEqual(self.w.model.understand_reconstruction.call_count,1);self.assertEqual(self.t['settings']['trial_width'],50);self.assertEqual(self.t['settings']['center'],807.5);self.assertIn('757.5–857.5','\n'.join(m['text'] for m in self.t['messages']));self.assertFalse(self.jobs)
 def test_model_offline_cannot_fall_back_to_fixed_reply(self):
  self.seed();self.w.model_ready=False
  with patch.object(self.w.sop,'handle',side_effect=AssertionError('No fallback')):self.w.submit_text(self.t,'please ±50');self.pump()
  self.assertEqual(self.t['settings']['trial_width'],10);self.assertIn('not ready',self.t['messages'][-1]['text']);self.assertFalse(self.jobs)
 def test_failed_interpretation_invalidates_old_confirmation(self):
  self.seed();self.t['sop']['center_valid']=True;self.w.sop.review(self.t);self.w.model.understand_reconstruction.side_effect=ValueError('Missing half-width')
  self.w.submit_text(self.t,'please ±50');self.pump();self.assertEqual(self.t['sop']['phase'],'edit_error');self.assertNotIn('review_fingerprint',self.t['sop']);self.assertFalse(self.jobs)
 def test_clear_parameters_are_processed_by_model_every_time(self):
  self.seed()
  self.send('make it twice as wide',turn(updates={'trial_width':20.}));self.send('step two',turn(updates={'trial_step':2.}));self.assertEqual(self.w.model.understand_reconstruction.call_count,2);self.assertEqual(self.t['settings']['trial_width'],20);self.assertEqual(self.t['settings']['trial_step'],2);self.assertFalse(self.jobs)
 def test_model_center_only_operation_implies_automatic_search_without_extra_mode_question(self):
  self.seed();self.t['sop']['mode']=None
  self.send('Only find center automatically, prompt particle, do not reconstruct',turn('request',{'prompt':'particle'},operation='find_center'))
  self.assertEqual(self.t['sop']['phase'],'search_offer');self.assertTrue(self.t['sop']['center_only']);self.assertFalse(self.t['sop']['full_requested']);self.assertFalse(self.jobs)
 def test_model_clarification_does_not_touch_settings(self):
  self.seed();before=copy.deepcopy(self.t['settings']);self.send('use fifty',turn('clarify',message='Do you mean half-width or step?'));self.assertEqual(self.t['settings'],before);self.assertIn('half-width or step',self.t['messages'][-1]['text'])
 def test_explicit_generate_uses_new_range_but_setting_only_does_not(self):
  self.seed();self.send('generate candidates with ±50 step1',turn('execute',{'trial_width':50.,'trial_step':1.},operation='try_center'));self.assertEqual(len(self.jobs),1);self.assertEqual(self.jobs[0][0]['action'],'try_center');self.assertEqual(self.jobs[0][1]['trial_width'],50.)
 def test_source_is_read_only_after_model_interpretation(self):
  self.send(f'"{self.source}" reconstruct it',turn('request',{'input_hdf5':str(self.source)},operation='reconstruct'))
  self.assertEqual(self.w.model.understand_reconstruction.call_count,1);self.assertEqual(self.t['metadata']['width'],1616);self.assertEqual(self.t['sop']['phase'],'geometry');self.assertFalse(self.jobs)
 def test_simple_geometry_and_mode_answers_also_call_model(self):
  self.seed('geometry');self.t['sop'].update(mode=None,geometry_confirmed=False)
  self.send('tomo',turn(updates={'geometry':'tomography'}));self.assertEqual(self.t['sop']['phase'],'mode')
  self.send('manual',turn(mode='manual'));self.assertEqual(self.t['sop']['phase'],'trial_offer');self.assertEqual(self.w.model.understand_reconstruction.call_count,2)
 def test_explicit_timing_pilot_uses_model_and_never_starts_full_data(self):
  self.seed();self.t['sop']['center_valid']=True;self.w.sop.review(self.t)
  self.send('measure time first',turn('execute',operation='measure_time'))
  self.assertEqual(self.w.model.understand_reconstruction.call_count,1);self.assertEqual(self.t['sop']['active_stage'],'pilot');self.assertEqual(len(self.jobs),1);self.assertEqual(self.jobs[0][1]['end_row']-self.jobs[0][1]['start_row'],4)
 def test_yes_but_gpu_one_requires_new_review(self):
  self.seed();self.t['sop']['center_valid']=True;self.w.sop.review(self.t);self.send('yes but GPU 1',turn(updates={'gpu':1}));self.assertEqual(self.t['sop']['phase'],'confirm');self.assertFalse(self.jobs)
  self.send('yes please',turn('confirm'));self.assertEqual(len(self.jobs),1);self.assertEqual(self.jobs[0][1]['gpu'],1);self.assertEqual(self.w.model.understand_reconstruction.call_count,2)
 def test_cancellation_during_understanding_discards_late_updates(self):
  self.seed();started=threading.Event();release=threading.Event()
  def understand(*args):started.set();release.wait(3);return turn(updates={'trial_width':50}),{'model_called':True}
  self.w.model.understand_reconstruction.side_effect=understand;self.w.submit_text(self.t,'make half-width 50');self.assertTrue(started.wait(1));self.w.stop_task(self.t);release.set();self.pump();self.assertEqual(self.t['settings']['trial_width'],10);self.assertFalse(self.jobs)
 def test_degree_range_is_not_applied_to_rotation_center(self):
  self.seed();self.t['settings'].update(geometry='laminography',lamino_angle=-20);self.t['sop'].update(trial_kind='angle',angle_confirmed=True,center_valid=True)
  self.send('-20 ± 2 degrees, step .25',turn(updates={'lamino_angle':-20.,'trial_width':2.,'trial_step':.25}));self.assertEqual(self.t['settings']['center'],807.5);self.assertEqual(self.t['settings']['trial_width'],2.)
 def test_explain_uses_model_without_entering_parameter_rules(self):
  self.seed();self.send('why 10?',turn('explain',message='10 is only the proposed initial half-width, not a measured optimum.'));self.assertIn('proposed initial',self.t['messages'][-1]['text']);self.assertEqual(self.t['settings']['trial_width'],10.)

class ReconstructionInterpretationTests(unittest.TestCase):
 def setUp(self):
  from assistant_lab.conversations import new_task
  self.t=new_task();self.t['settings']['center']=807.5;self.t['sop']={'phase':'trial_offer','mode':'manual'}
 def test_missing_explicit_new_step_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'step'):parse_turn(packet(updates={'trial_width':50}),'807.5 ±50 step2',self.t)
 def test_negated_old_step_does_not_override_model_understanding(self):
  t=parse_turn(packet(updates={'trial_step':2}),'Do not use step 1, use 2 instead',self.t);self.assertEqual(t['updates']['trial_step'],2)
 def test_missing_half_width_is_rejected_instead_of_repeating_old_default(self):
  with self.assertRaisesRegex(ValueError,'missed'):parse_turn(packet(updates={'trial_step':1}),'please 807.5 ±50 step1',self.t)
 def test_exact_range_and_ascii_variant_are_valid(self):
  for text in ('please 807.5 ± 50 px, step 1','807.5 +/- 50 step1'):
   t=parse_turn(packet(updates={'trial_width':50,'trial_step':1}),text,self.t);self.assertEqual(t['updates']['trial_width'],50)
 def test_unknown_fields_and_invented_paths_are_rejected(self):
  with self.assertRaises(ValueError):parse_turn(packet(updates={'input_hdf5':'D:/invented.h5'}),'reconstruct it',self.t)
  with self.assertRaises(ValueError):parse_turn(packet(updates={'shell':'delete data'}),'hi',self.t)
 def test_schema_retries_incomplete_interpretation(self):
  model=ChatModel();bad=packet(updates={'trial_step':1});good=packet(updates={'trial_width':50,'trial_step':1})
  with patch.object(model,'structured_reply',side_effect=[{'content':json.dumps(bad)},{'content':json.dumps(good)}]) as reply:
   t,meta=model.understand_reconstruction('807.5 ±50 step1',self.t)
  self.assertEqual(reply.call_count,2);self.assertEqual(t['updates']['trial_width'],50);self.assertTrue(meta['model_called'])
 def test_confirm_cannot_hide_parameter_edits(self):
  with self.assertRaises(ValueError):parse_turn(packet('confirm',{'gpu':1}),'yes but GPU1',self.t)
