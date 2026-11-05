import copy,json,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
import h5py
from PySide6.QtWidgets import QApplication
import test_reconstruction_sop as fixtures
from assistant_lab.jobs import atomic_json
from assistant_lab.reconstruction_sop import estimate,timing_key
from assistant_lab.trial_candidates import selection
from assistant_lab.results import answer_result,result_context

class WorkflowEdges(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 setUp=fixtures.SOPTests.setUp;tearDown=fixtures.SOPTests.tearDown;pump=fixtures.SOPTests.pump;send=fixtures.SOPTests.send;prepare=fixtures.SOPTests.prepare;complete=fixtures.SOPTests.complete
 def test_angle_only_spelling_supplies_lamino_geometry(self):
  self.prepare(f'Reconstruct "{self.source}" lamino angle -20 center 31.5 rows 8 to 12.')
  self.assertEqual(self.t['sop']['phase'],'confirm');self.assertEqual(self.t['settings']['geometry'],'laminography')
 def test_auto_range_and_initial_step_are_both_bound(self):
  self.prepare(f'Only find center automatically in "{self.source}" using tomo, prompt particle, range 28 to 32 step 1.')
  self.assertEqual(self.t['settings']['range_low'],28);self.assertEqual(self.t['settings']['range_high'],32);self.assertEqual(self.t['settings']['initial_step'],1)
 def test_prep_settings_are_visible_in_confirmation(self):
  self.prepare();self.send('dezinger 5 bright ratio 0.4 stripes off')
  self.assertEqual(self.t['settings']['dezinger'],5);self.assertEqual(self.t['settings']['bright_ratio'],.4);self.assertEqual(self.t['settings']['remove_stripe_method'],'none');self.assertIn('dezinger 5',self.t['messages'][-1]['text'])
 def test_stopping_pending_metadata_does_not_start_any_job(self):
  self.w.sop.bootstrap(self.t);self.t['sop']['phase']='reading';self.w.stop_task(self.t)
  self.assertEqual(self.t['sop']['phase'],'paused');self.assertTrue(self.t['cancel_requested']);self.assertFalse(self.calls)
 def test_confirmed_plan_stays_in_history_after_start(self):
  self.prepare();plan=self.t['messages'][-1]['text'];self.send('yes');self.assertTrue(any(m['text']==plan for m in self.t['messages']))
 def test_segment_results_creates_new_task_and_preserves_reconstruction(self):
  self.prepare();self.send('yes');job=self.t['jobs'][-1];folder=Path(job['job_dir'])/'results/reconstruction';folder.mkdir(parents=True)
  import tifffile,numpy as np
  tifffile.imwrite(folder/'recon.tiff',np.ones((8,8),np.float32))
  self.complete({'center':31.5,'slices':2,'folder':str(folder)})
  old=self.t['id'];self.send('segment these results');new=self.w.current
  self.assertNotEqual(new['id'],old);self.assertEqual(new['kind'],'segment');self.assertEqual(Path(new['settings']['image_folder']),folder);self.assertEqual(self.t['sop']['phase'],'complete');self.assertEqual(len(self.calls),1)
 def test_known_center_segment_all_asks_feature_then_one_confirmation(self):
  self.prepare(f'Reconstruct "{self.source}" using tomo center 31.5 rows 8 to 12, segment all.')
  self.assertEqual(self.t['sop']['phase'],'target');self.assertFalse(self.calls);self.send('particle');self.assertEqual(self.t['sop']['phase'],'confirm');self.assertIn('Segment All: yes',self.t['messages'][-1]['text']);self.send('yes');self.assertTrue(self.calls[-1][1]['segment_all']);self.assertEqual(self.calls[-1][0]['action'],'reconstruct')
 def test_invalid_initial_rows_can_be_corrected_in_chat(self):
  self.prepare(f'Reconstruct "{self.source}" using tomo center 31.5 rows 100 to 110.')
  self.assertEqual(self.t['sop']['phase'],'parameters');self.send('rows 8 to 12');self.assertEqual(self.t['sop']['phase'],'confirm');self.assertFalse(self.calls)
 def test_changing_tilt_keeps_known_center_when_geometry_is_unchanged(self):
  self.prepare(f'Reconstruct "{self.source}" using lamino tilt angle -20 center 31.5 rows 8 to 12.')
  self.send('lamino angle -21');self.assertEqual(self.t['settings']['center'],31.5);self.assertEqual(self.t['settings']['lamino_angle'],-21);self.assertEqual(self.t['sop']['phase'],'confirm')
 def test_find_angle_routes_to_trials_and_preserves_full_method(self):
  self.prepare(f'Find laminography angle for "{self.source}", center 31.5, tilt angle -20.')
  self.assertEqual(self.t['sop']['phase'],'trial_offer');self.assertEqual(self.t['sop']['trial_kind'],'angle');self.send('generate candidates');self.assertEqual(self.calls[-1][0]['action'],'try_angle');self.assertEqual(self.t['settings']['method'],'fourierrec')
 def test_signed_negative_tilt_and_natural_confirmation(self):
  self.prepare(f'Reconstruct "{self.source}" using lamino, tilt angle -20, center 31.5, rows 8 to 12, 2x2 binning.')
  self.assertEqual(self.t['sop']['phase'],'confirm');self.send('yes, go ahead');self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][1]['lamino_angle'],-20)
 def test_range_in_initial_command_is_preserved(self):
  self.prepare(f'Reconstruct "{self.source}" using tomo, manual, range 28 to 32 step 1, rows 8 to 12.')
  self.assertEqual(self.t['settings']['center'],30);self.assertEqual(self.t['settings']['trial_width'],2);self.assertEqual(self.t['settings']['trial_step'],1)
 def test_only_center_search_waits_after_success_even_when_yes_follows(self):
  self.prepare(f'Only find center automatically in "{self.source}" using tomo, prompt particle, do not reconstruct.')
  self.assertEqual(self.t['sop']['phase'],'search_offer');self.send('start center search');self.assertEqual(self.calls[-1][0]['action'],'find_center')
  self.complete({'recommended_center':31.25,'folder':str(self.r)})
  self.assertEqual(self.t['sop']['phase'],'center_ready');before=len(self.calls);self.send('yes');self.assertEqual(len(self.calls),before)
  self.send('reconstruct all');self.assertEqual(self.t['sop']['phase'],'confirm');self.assertEqual(self.t['settings']['end_row'],32)
 def test_invalid_edit_invalidates_confirmation_without_partial_updates(self):
  self.prepare();before=copy.deepcopy(self.t['settings']);self.send('GPU -1')
  self.assertEqual(self.t['settings'],before);self.assertEqual(self.t['sop']['phase'],'edit_error');self.send('yes');self.assertFalse(self.calls);self.assertEqual(self.t['sop']['phase'],'confirm')
 def test_switch_to_lamino_requires_angle_and_new_center(self):
  self.prepare();self.send('use lamino');self.assertEqual(self.t['sop']['phase'],'angle');self.assertEqual(self.t['settings']['center'],0)
  self.send('-20');self.assertEqual(self.t['sop']['phase'],'trial_offer');self.assertFalse(self.calls)
 def test_zero_lamino_angle_does_not_launch(self):
  self.prepare(f'Reconstruct "{self.source}" using lamino, tilt angle 0, center 31.5.');self.send('yes');self.assertFalse(self.calls)
 def test_failed_trial_retry_does_not_switch_to_full_reconstruction(self):
  self.prepare(f'Reconstruct "{self.source}" using tomo manual.');self.send('generate candidates')
  j=self.t['jobs'][-1];atomic_json(Path(j['job_dir'])/'job_status.json',{'state':'failed','error':'test failure'});self.w.poll();self.pump();self.send('retry')
  self.assertEqual(self.t['sop']['phase'],'trial_offer');self.assertEqual(len(self.calls),1)
 def test_confirmation_edits_apply_before_second_confirmation(self):
  self.prepare();self.send('ok but GPU 1');self.assertFalse(self.calls);self.assertEqual(self.t['settings']['gpu'],1);self.send('yes');self.assertEqual(self.calls[-1][1]['gpu'],1)
 def test_complete_automatic_review_describes_unknown_center_honestly(self):
  self.prepare(f'Automatically reconstruct "{self.source}" using tomo, prompt particle.')
  self.assertIn('automatic SAM3 search',self.t['messages'][-1]['text']);self.assertNotIn('Center: 0 px',self.t['messages'][-1]['text'])
 def test_segment_all_and_no_segmentation_are_explicit(self):
  self.prepare(f'Automatically reconstruct "{self.source}" using tomo, prompt particle, segment all.')
  self.assertTrue(self.t['settings']['segment_all']);self.send('no segmentation');self.assertFalse(self.t['settings']['segment_all']);self.assertFalse(self.calls)
 def test_paths_with_spaces_are_read_as_one_source(self):
  path=self.r/'name with spaces.h5';self.source.rename(path);self.send(str(path));self.assertEqual(self.t['settings']['input_hdf5'],str(path).replace('\\','/'));self.assertEqual(self.t['sop']['phase'],'geometry')
 def test_multiple_sources_preserve_original_explicit_request(self):
  self.send(f'Reconstruct "{self.source}" or "{self.other}" using tomo, center 31.5, rows 8 to 12.')
  self.assertEqual(self.t['sop']['phase'],'file');self.send('2');self.assertEqual(Path(self.t['settings']['input_hdf5']),self.other);self.assertEqual(self.t['sop']['phase'],'confirm')
 def test_folder_indices_are_one_based_in_both_languages(self):
  self.send(str(self.r));text=self.t['messages'][-1]['text'];self.assertIn('1. ',text);self.assertNotIn('0. ',text)
 def test_model_loading_does_not_prevent_metadata_cancel_from_send_button(self):
  entered=threading.Event();release=threading.Event()
  def inspect(*args):entered.set();release.wait(3);return {'rows':32,'width':64,'projections':7}
  with patch('assistant_lab.reconstruction_sop.inspect_source',side_effect=inspect):
   self.w.submit_text(self.t,str(self.source));self.assertTrue(entered.wait(1));self.w.composer.setPlainText('cancel');self.assertTrue(self.w.send_btn.isEnabled());self.w.send_btn.click();release.set();self.pump()
  self.assertEqual(self.t['sop']['phase'],'paused');self.assertFalse(self.calls)
 def test_timing_cache_invalidates_on_same_path_file_change(self):
  self.prepare();key=timing_key(self.t);self.t['sop']['timings']=[{'key':key,'seconds':4,'slices':2}]
  with patch('assistant_lab.reconstruction_sop.STATE_ROOT',self.r/'state'):
   self.assertIn('extrapolated',estimate(self.t))
   with h5py.File(self.source,'a') as h:h.attrs['changed']='new'
   self.assertIn('no matching measurement',estimate(self.t))
 def test_result_queries_never_reuse_previous_input(self):
  self.prepare();self.send('yes');self.complete({'center':31.5,'slices':2,'folder':str(self.r)})
  self.assertIn('31.5',answer_result(self.t,'center')[0]);self.send(str(self.other));self.assertEqual(result_context(self.t),[])
 def test_stale_running_phase_restores_to_interrupted(self):
  self.prepare();self.t['sop']['phase']='running';self.t['state']='failed';self.w.sop.restore(self.t);self.assertEqual(self.t['sop']['phase'],'interrupted');self.assertFalse(self.calls)
 def test_external_flat_is_not_misinterpreted_as_alternative_input(self):
  self.send(f'Reconstruct "{self.source}" using flat file "{self.other}" with tomo center 31.5.')
  self.assertFalse(self.calls);self.assertIn('separate flat-file',self.t['messages'][-1]['text']);self.assertFalse(self.t.get('sop',{}).get('source'))
 def test_ambiguous_trial_numbers_and_explicit_positive_angle(self):
  items=[{'index':1,'value':2.,'file':'a.tiff'},{'index':2,'value':3.,'file':'b.tiff'},{'index':3,'value':4.,'file':'c.tiff'}]
  self.assertEqual(selection('angle 2',items,64,'angle')[0],2.)
  self.assertIsNone(selection('第二张或者第三张',items,64)[0]);self.assertIsNotNone(selection('last',[],64)[1])
 def test_question_about_center_does_not_create_a_reconstruction_workflow(self):
  with patch.object(self.w.model,'plan') if hasattr(self.w.model,'plan') else patch.object(self.w,'model_ready',False):
   self.send('What is a rotation center?')
  self.assertFalse(self.calls);self.assertFalse(self.w.sop.enabled(self.t))
