"""Task-bound GUI links, read-only previews and explicit parameter handoff."""
import os,copy,tempfile,time,hashlib,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import h5py,numpy as np,tifffile
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from assistant_lab.chat_window import ChatWindow
from assistant_lab.conversations import Conversations,inspect_source,mark
from assistant_lab.jobs import JobStore,atomic_json
from assistant_lab.data_viewers import read_hdf5,file_stamp,image_files
from assistant_lab.trial_candidates import catalogue
from assistant_lab.viewer_links import attach_tool,apply_input,apply_candidate

class ViewerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=self.root/'data.h5'
  self.data=np.arange(5*16*32,dtype=np.uint16).reshape(5,16,32)
  with h5py.File(self.path,'w') as h:
   h['exchange/data']=self.data;h['exchange/data_white']=np.ones((2,16,32),np.uint16)*5000;h['exchange/data_dark']=np.zeros((1,16,32),np.uint16);h['exchange/theta']=np.arange(5,dtype=float)*90
  self.before=hashlib.sha256(self.path.read_bytes()).hexdigest();self.w=ChatWindow(Conversations(self.root/'conversations'),JobStore(self.root/'jobs'),autoload=False);self.w.new_task();self.t=self.w.current;s=self.t['settings'];s.update(input_hdf5=str(self.path),start_row=0,end_row=16,output_root=str(self.root/'jobs'));self.t['metadata']=inspect_source('input_hdf5',self.path);mark(self.t,'rows','input_hdf5');self.w.sop.bootstrap(self.t);self.t['sop'].update(source=str(self.path),source_stat=file_stamp(self.path),phase='geometry',geometry_confirmed=False,overview_shown=True);self.w.show();self.pump(.05)
 def pump(self,seconds=.1):
  end=time.monotonic()+seconds
  while time.monotonic()<end:self.app.processEvents();time.sleep(.005)
 def wait(self,predicate):
  end=time.monotonic()+5
  while not predicate() and time.monotonic()<end:self.pump(.02)
  self.assertTrue(predicate())
 def tearDown(self):
  for dialog in list(self.w.viewer_windows.values()):dialog.close()
  self.pump(.03);self.w.close();QThreadPool.globalInstance().waitForDone(5000);self.pump(.03);self.tmp.cleanup()
 def link(self,kind='input',source=None,job=None):
  self.w.add(self.t,'assistant','Data ready.');attach_tool(self.w,self.t,kind,source or self.path,job);entry=self.t['messages'][-1];return entry,entry['tools'][-1]
 def open(self,entry,tool):return self.w.open_viewer(self.t['id'],entry['id'],tool['id'])
 def trial(self,angle=False):
  folder=self.root/'jobs/trial';folder.mkdir(parents=True);files=[]
  for val in ([-19.,-21.,-20.] if angle else [14.,10.,12.]):
   path=folder/f"recon_slice0008_{'angle' if angle else 'center'}{val:.2f}.tiff";tifffile.imwrite(path,np.ones((12,12),np.float32)*val+np.arange(144,dtype=np.float32).reshape(12,12)/1000);files.append(str(path))
  items=catalogue(files);job={'id':'trial','job_dir':str(folder),'action':'try_angle' if angle else 'try_center','reported':True};self.t['jobs']=[job];self.t['sop'].update(phase='choose_angle' if angle else 'choose',geometry_confirmed=True,mode='manual',candidates=items,trial_kind='angle' if angle else 'center',source_stat=file_stamp(self.path));self.t['settings']['center']=16
  if angle:self.t['settings'].update(geometry='laminography',lamino_angle=-20);self.t['sop']['angle_confirmed']=True
  atomic_json(folder/'job.json',dict(id='trial',settings=self.t['settings']));atomic_json(folder/'job_status.json',dict(state='succeeded',result=dict(candidate_catalogue=items,files=files,folder=str(folder))))
  entry,tool=self.link('trials',folder,job);return items,entry,tool
 def test_metadata_link_opens_a_nonmodal_viewer_and_reads_uint16(self):
  entry,tool=self.link();self.w.views[entry['id']].tool_links.linkActivated.emit(tool['id']);dialog=next(iter(self.w.viewer_windows.values()));self.assertFalse(dialog.isModal());self.wait(lambda:dialog.array is not None);self.assertEqual(dialog.array[0,0],self.data[2,0,0]);self.assertIn('uint16',dialog.image_info.text());self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.before)
 def test_picking_a_projection_row_updates_the_pending_search_and_trial_rows(self):
  entry,tool=self.link();dialog=self.open(entry,tool);dialog.canvas.row_picked.emit(.25);self.assertEqual(dialog.fields['search_row'].value(),4)
  dialog.geometry.setCurrentIndex(1);dialog.mode.setCurrentIndex(1);dialog.apply_button.click();self.pump();self.assertEqual(self.t['settings']['search_row'],4);self.assertEqual(self.t['settings']['trial_row'],4)
 def test_applying_unchanged_parameters_keeps_a_pending_trial_selection(self):
  self.trial();entry,tool=self.link();dialog=self.open(entry,tool);before=copy.deepcopy(self.t['settings']);dialog.apply_button.click();self.assertEqual(self.t['settings'],before);self.assertEqual(self.t['sop']['phase'],'choose');self.assertIn('No parameter changes',dialog.status.text())
 def test_duplicate_link_reuses_the_same_window(self):
  entry,tool=self.link();first=self.open(entry,tool);self.assertIs(self.open(entry,tool),first);self.assertEqual(len(self.w.viewer_windows),1)
 def test_unknown_link_and_user_text_are_not_executable_links(self):
  entry,tool=self.link();self.assertIsNone(self.w.open_viewer(self.t['id'],entry['id'],'not-a-tool'));self.w.add(self.t,'user','momobot://input/secret');user=self.t['messages'][-1];user['tools']=[tool];self.w.render();self.assertIsNone(self.w.open_viewer(self.t['id'],user['id'],tool['id']))
 def test_projection_flat_dark_navigation_uses_the_right_dataset(self):
  entry,tool=self.link();dialog=self.open(entry,tool);self.wait(lambda:dialog.array is not None);dialog.source.setCurrentText('Flat');self.wait(lambda:dialog.array is not None and dialog.loaded_key[1]=='Flat');self.assertEqual(dialog.array[0,0],5000);dialog.source.setCurrentText('Dark');self.wait(lambda:dialog.array is not None and dialog.loaded_key[1]=='Dark');self.assertEqual(dialog.array[0,0],0)
 def test_input_parameters_are_applied_transactionally_without_running(self):
  entry,tool=self.link();dialog=self.open(entry,tool);dialog.geometry.setCurrentIndex(1);dialog.mode.setCurrentIndex(1);dialog.fields['center'].setValue(15.5);dialog.fields['start_row'].setValue(2);dialog.fields['end_row'].setValue(12);dialog.binning.setCurrentIndex(1)
  with patch.object(JobStore,'submit') as submit:dialog.apply_button.click();self.pump();submit.assert_not_called()
  self.assertEqual(self.t['settings']['center'],15.5);self.assertEqual(self.t['settings']['binning'],1);self.assertEqual(self.t['sop']['phase'],'confirm');self.assertIn('Applied from Data Viewer','\n'.join(m['text'] for m in self.t['messages']));self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.before)
 def test_invalid_row_edit_does_not_partially_change_task(self):
  entry,tool=self.link();dialog=self.open(entry,tool);before=copy.deepcopy(self.t['settings']);dialog.fields['start_row'].setValue(14);dialog.fields['end_row'].setValue(2);dialog.fields['gpu'].setValue(1);dialog.apply_button.click();self.pump();self.assertEqual(self.t['settings'],before);self.assertTrue(dialog.status.text());self.assertFalse(self.t['jobs'])
 def test_changing_input_while_viewer_is_open_prevents_wrong_task_write(self):
  entry,tool=self.link();dialog=self.open(entry,tool);self.t['settings']['input_hdf5']='D:/another.h5';before=copy.deepcopy(self.t['settings']);dialog.fields['gpu'].setValue(1);dialog.apply_button.click();self.assertEqual(self.t['settings'],before);self.assertIn('different input',dialog.status.text())
 def test_modified_input_file_is_rejected(self):
  entry,tool=self.link()
  with h5py.File(self.path,'a') as h:h.attrs['changed']=True
  self.assertIsNone(self.open(entry,tool));self.assertIn('changed',self.w.statusBar().currentMessage())
  with self.assertRaisesRegex(ValueError,'changed'):read_hdf5(self.path,'Projection',0,tool['source_stat'])
 def test_deleted_task_cannot_accept_open_viewer_edits(self):
  entry,tool=self.link();dialog=self.open(entry,tool);self.t['_deleted']=True;dialog.fields['gpu'].setValue(1);dialog.apply_button.click();self.assertIn('deleted',dialog.status.text())
 def test_selection_targets_its_original_task_after_chat_switch(self):
  items,entry,tool=self.trial();self.w.new_task();other=self.w.current;before=copy.deepcopy(other['settings']);apply_candidate(self.w,self.t,tool,items[1]);self.assertEqual(self.t['settings']['center'],12);self.assertEqual(other['settings'],before);self.assertEqual(self.w.current_id,self.t['id'])
 def test_trial_gui_selects_the_exact_candidate_and_only_reviews(self):
  items,entry,tool=self.trial();dialog=self.open(entry,tool);dialog.frame.setValue(3);self.wait(lambda:dialog.array is not None and dialog.loaded_key==dialog.request_key)
  with patch.object(JobStore,'submit') as submit:dialog.use_button.click();self.pump();submit.assert_not_called()
  self.assertEqual(self.t['settings']['center'],14);self.assertEqual(self.t['sop']['phase'],'confirm');self.assertEqual(self.t['sop']['selection']['value'],14)
 def test_angle_trial_handoff_preserves_rotation_center(self):
  items,entry,tool=self.trial(True)
  # Older backend filenames could describe angle trials using a center suffix.
  from assistant_lab.jobs import read_json
  status_path=Path(self.t['jobs'][0]['job_dir'])/'job_status.json';status=read_json(status_path)
  for item in status['result']['candidate_catalogue']:item['quantity']='center'
  atomic_json(status_path,status);dialog=self.open(entry,tool);dialog.frame.setValue(3);self.wait(lambda:dialog.array is not None and dialog.loaded_key==dialog.request_key);self.assertEqual(dialog.use_button.text(),'Use this angle');dialog.use_button.click();self.pump();self.assertEqual(self.t['settings']['lamino_angle'],-19);self.assertEqual(self.t['settings']['center'],16);self.assertEqual(self.t['sop']['phase'],'confirm')
 def test_old_trial_link_cannot_replace_new_trial_selection(self):
  items,entry,tool=self.trial();self.t['jobs'].append(dict(id='newer',action='try_center',job_dir=str(self.root/'newer')));before=self.t['settings']['center']
  with self.assertRaisesRegex(ValueError,'older'):apply_candidate(self.w,self.t,tool,items[0])
  self.assertEqual(self.t['settings']['center'],before)
 def test_trial_file_change_requires_reloading_before_selection(self):
  items,entry,tool=self.trial();dialog=self.open(entry,tool);self.wait(lambda:dialog.array is not None);chosen=dialog.items[dialog.frame.value()-1];Path(chosen['file']).write_bytes(b'changed');dialog.use_button.click();self.assertIn('changed',dialog.status.text());self.assertEqual(self.t['settings']['center'],16)
 def test_float_reconstruction_browsing_is_natural_sorted_and_read_only(self):
  folder=self.root/'results';folder.mkdir()
  for n in (10,2,1):tifffile.imwrite(folder/f'recon_{n}.tiff',np.ones((20,20),np.float32)*n/1e8)
  self.assertEqual([p.name for p in image_files(folder)],['recon_1.tiff','recon_2.tiff','recon_10.tiff']);jobfolder=self.root/'jobs/full';jobfolder.mkdir(parents=True);job={'id':'full','job_dir':str(jobfolder),'action':'reconstruct'};self.t['jobs']=[job];atomic_json(jobfolder/'job.json',dict(id='full',settings=self.t['settings']));atomic_json(jobfolder/'job_status.json',dict(state='succeeded',result=dict(folder=str(folder))))
  entry,tool=self.link('results',folder,job);dialog=self.open(entry,tool);self.wait(lambda:dialog.array is not None);dialog.frame.setValue(3);self.wait(lambda:dialog.array is not None and dialog.loaded_key==dialog.request_key);self.assertIn('recon_10',dialog.image_info.text());self.assertEqual(tifffile.imread(folder/'recon_10.tiff').dtype,np.float32);self.assertFalse(dialog.use_button.isVisible());self.assertIsNotNone(dialog.canvas.item)
 def test_result_browser_handles_files_arriving_during_reconstruction(self):
  folder=self.root/'new_results';jobfolder=self.root/'jobs/full';jobfolder.mkdir(parents=True);job={'id':'full','job_dir':str(jobfolder),'action':'reconstruct'};self.t['jobs']=[job];atomic_json(jobfolder/'job.json',dict(id='full',settings=self.t['settings']));atomic_json(jobfolder/'job_status.json',dict(state='running'))
  entry,tool=self.link('results',folder,job);dialog=self.open(entry,tool);self.wait(lambda:not dialog.scanning);self.assertFalse(dialog.items);folder.mkdir();tifffile.imwrite(folder/'slice.tiff',np.arange(64,dtype=np.float32).reshape(8,8));dialog.refresh();self.wait(lambda:dialog.array is not None);self.assertEqual(len(dialog.items),1)
 def test_new_slices_arriving_out_of_order_preserve_the_selected_file(self):
  from assistant_lab.data_viewers import ResultBrowser
  folder=self.root/'arriving';folder.mkdir();tifffile.imwrite(folder/'slice10.tiff',np.ones((8,8),np.float32)*10)
  dialog=ResultBrowser(self.w,dict(kind='results',source=str(folder)));self.w.viewer_windows['test_arriving']=dialog;dialog.show();self.wait(lambda:dialog.array is not None);tifffile.imwrite(folder/'slice1.tiff',np.ones((8,8),np.float32));dialog.refresh();self.wait(lambda:len(dialog.items)==2 and dialog.array is not None and dialog.loaded_key==dialog.request_key);self.assertIn('slice10',dialog.image_info.text())
 def test_trial_display_range_can_be_locked_across_candidates(self):
  items,entry,tool=self.trial();dialog=self.open(entry,tool);self.wait(lambda:dialog.array is not None);limits=(dialog.low.value(),dialog.high.value());dialog.canvas.scale(2,2);zoom=dialog.canvas.transform().m11();dialog.frame.setValue(3);self.wait(lambda:dialog.array is not None and dialog.loaded_key==dialog.request_key);self.assertEqual((dialog.low.value(),dialog.high.value()),limits);self.assertAlmostEqual(dialog.canvas.transform().m11(),zoom,places=4)
 def test_rapid_navigation_keeps_latest_frame_and_bounded_cache(self):
  entry,tool=self.link();dialog=self.open(entry,tool)
  for n in (1,5,2,4):dialog.frame.setValue(n)
  self.wait(lambda:dialog.array is not None and dialog.loaded_key==dialog.request_key);self.assertEqual(dialog.array[0,0],self.data[3,0,0]);self.assertLessEqual(len(dialog.cache),4);self.assertFalse(self.w.busy)
 def test_old_conversation_gets_links_without_rerunning_trials(self):
  items,entry,tool=self.trial();entry.pop('tools');self.w.select_task(self.t['id']);self.assertTrue(any(x.get('kind')=='trials' for m in self.t['messages'] for x in m.get('tools',[])));self.assertEqual(self.t['sop']['phase'],'choose')
 def test_browsing_completed_trial_does_not_offer_to_override_a_later_plan(self):
  items,entry,tool=self.trial();self.t['sop']['phase']='complete';dialog=self.open(entry,tool);self.wait(lambda:dialog.array is not None);self.assertFalse(dialog.use_button.isEnabled())
 def test_links_persist_with_conversation_metadata(self):
  entry,tool=self.link();saved=self.w.repo.all()[0];self.assertEqual(saved['messages'][-1]['tools'][0],tool)

if __name__=='__main__':unittest.main()
