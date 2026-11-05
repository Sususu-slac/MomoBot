import os,sys,time,json,tempfile,copy,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from assistant_lab.conversations import *
from assistant_lab.chat_window import ChatWindow
from assistant_lab.protocol import Plan
from assistant_lab.jobs import JobStore,atomic_json

def sourced(kind='reconstruct'):
    t=new_task();choose_kind(t,kind)
    field='image_folder' if kind=='segment' else 'dataset' if kind in ('train','prepare_dataset') else 'input_hdf5'
    set_source(t,field,'D:/chosen');accept_source(t,field,'D:/chosen',{'rows':2048,'width':2048,'projections':901} if field=='input_hdf5' else {'images':12,'needs_split':True})
    return t

class FlowTests(unittest.TestCase):
    def test_new_task_has_no_inherited_source_or_center(self):
        t=new_task();self.assertEqual(t['settings']['center'],0);self.assertFalse(t['settings']['input_hdf5']);self.assertEqual(step(t),'kind')
    def test_reconstruction_guide_requires_explicit_rows_and_center(self):
        t=sourced();self.assertEqual(step(t),'center_mode')
        apply_response(t,Plan('set_parameters',{'center':1028.75},''));self.assertEqual(step(t),'rows')
        apply_response(t,Plan('set_parameters',{},''),row_scope='middle');self.assertEqual((t['settings']['start_row'],t['settings']['end_row']),(1022,1027));self.assertEqual(step(t),'ready');self.assertEqual(action(t),'reconstruct')
    def test_automatic_center_adds_prompt_and_selects_analyze(self):
        t=sourced();apply_response(t,Plan('set_parameters',{},''),center_mode='auto',row_scope='all');self.assertEqual(step(t),'prompt')
        apply_response(t,Plan('set_parameters',{'prompt':'particle'},''));self.assertEqual(step(t),'ready');self.assertEqual(action(t),'analyze');self.assertEqual(t['settings']['center'],0)
    def test_invalid_parameter_response_is_atomic(self):
        t=sourced();before=copy.deepcopy(t)
        with self.assertRaises(ValueError):apply_response(t,Plan('set_parameters',{'center':3000},''))
        self.assertEqual(t,before)
    def test_new_file_resets_old_center_and_row_confirmation(self):
        t=sourced();apply_response(t,Plan('set_parameters',{'center':1028.75},''),row_scope='middle');set_source(t,'input_hdf5','D:/different.h5')
        self.assertEqual(t['settings']['center'],0);self.assertNotIn('rows',t['done']);self.assertEqual(step(t),'input_hdf5')
    def test_segmentation_prompt_and_limit_are_separate_steps(self):
        t=sourced('segment');self.assertEqual(step(t),'prompt');apply_response(t,Plan('set_parameters',{'prompt':'particle'},''));self.assertEqual(step(t),'limit')
        apply_response(t,Plan('set_parameters',{'max_images':0},''));self.assertEqual(step(t),'ready');self.assertIn('Images: all',review(t))
    def test_raw_training_data_must_be_prepared_first(self):
        t=sourced('train');self.assertEqual(step(t),'split');apply_response(t,Plan('set_parameters',{'train_percent':80},''));self.assertEqual(step(t),'ready');self.assertEqual(action(t),'prepare_dataset')
        t['prepared']=True;t['needs_split']=False;self.assertEqual(step(t),'epochs');apply_response(t,Plan('set_parameters',{'epochs':2},''));self.assertEqual(action(t),'train');self.assertEqual(step(t),'ready')
    def test_default_acceptance_only_completes_current_step(self):
        t=sourced('segment');apply_response(t,Plan('set_parameters',{},''),accept_defaults=True);self.assertEqual(step(t),'limit');self.assertNotIn('limit',t['done'])
    def test_running_task_cannot_be_changed(self):
        t=sourced();t['state']='running'
        with self.assertRaises(ValueError):apply_response(t,Plan('set_parameters',{'center':1000},''))
    def test_uninspected_path_is_not_ready(self):
        t=new_task();choose_kind(t,'segment');apply_response(t,Plan('set_parameters',{'image_folder':'D:/new'},''));self.assertEqual(step(t),'image_folder')
    def test_conversation_restore_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Conversations(tmp);t=repo.create();message(t,'user','hello');repo.save(t);self.assertEqual(Conversations(tmp).all()[0]['messages'][-1]['text'],'hello')
    def test_unrelated_input_type_is_rejected(self):
        t=sourced('segment')
        with self.assertRaises(ValueError):apply_response(t,Plan('set_parameters',{'input_hdf5':'D:/other.h5'},''))
    def test_explicit_rows_survive_delayed_source_inspection(self):
        t=new_task();choose_kind(t,'reconstruct');apply_response(t,Plan('set_parameters',{'input_hdf5':'D:/data.h5','start_row':10,'end_row':15},''))
        accept_source(t,'input_hdf5','D:/data.h5',{'rows':100,'width':200,'projections':90});self.assertEqual(t['settings']['start_row'],10);self.assertEqual(t['settings']['end_row'],15)
    def test_impossible_explicit_rows_rejected_after_inspection(self):
        t=new_task();choose_kind(t,'reconstruct');apply_response(t,Plan('set_parameters',{'input_hdf5':'D:/data.h5','start_row':100,'end_row':105},''))
        with self.assertRaises(ValueError):accept_source(t,'input_hdf5','D:/data.h5',{'rows':100,'width':200,'projections':90})
        self.assertNotIn('input_hdf5',t['done'])
    def test_short_row_answers_bind_to_reconstruction_rows(self):
        from assistant_lab.answer_bindings import explicit_answer
        t=sourced();t['center_mode']='known';t['settings']['center']=1000
        self.assertEqual(explicit_answer('All slices.',t),({},{'row_scope':'all'}))
        self.assertEqual(explicit_answer('Five middle slices please.',t),({},{'row_scope':'middle'}))
    def test_explicit_confidence_and_questions(self):
        from assistant_lab.answer_bindings import explicit_answer
        t=sourced('segment');updates,_=explicit_answer('Only 1 image, with confidence 25 percent.',t);self.assertEqual(updates,{'max_images':1,'confidence':.25})
        self.assertEqual(explicit_answer('What does confidence 25 percent mean?',t),({},{}))
    def test_model_row_guess_is_replaced_by_explicit_choice(self):
        from assistant_lab.chat_model import ChatModel
        t=sourced();t['center_mode']='known';t['settings']['center']=1000
        raw={'plan':{'action':'set_parameters','updates':[{'field':'range_low','value':'1022'},{'field':'range_high','value':'1027'},{'field':'gpu','value':'0'}],'message':'Use all slices.'},'center_mode':'auto','row_scope':'unchanged','accept_defaults':False}
        with patch('assistant_lab.chat_model.post_json',side_effect=[{'prompt':'test'},{'content':json.dumps(raw)}]):p,c,m=ChatModel().converse('All slices.',t)
        self.assertFalse(p.updates);self.assertEqual(c['center_mode'],'unchanged');apply_response(t,p,c['center_mode'],c['row_scope'],c['accept_defaults']);self.assertEqual(t['settings']['end_row'],2048);self.assertEqual(t['settings']['start_row'],0);self.assertEqual(t['settings']['gpu'],0)
    def test_missing_explicit_confidence_is_recovered(self):
        from assistant_lab.chat_model import ChatModel
        t=sourced('segment');mark(t,'prompt')
        raw={'plan':{'action':'set_parameters','updates':[{'field':'max_images','value':'1'}],'message':'One image.'},'center_mode':'unchanged','row_scope':'unchanged','accept_defaults':False}
        with patch('assistant_lab.chat_model.post_json',side_effect=[{'prompt':'test'},{'content':json.dumps(raw)}]):p,c,m=ChatModel().converse('Only 1 image, with confidence 25 percent.',t)
        self.assertEqual(p.updates,{'max_images':1,'confidence':.25});self.assertTrue(m['normalizations'])

class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf');cls.app.setFont(QFont('Segoe UI',10))
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.w=ChatWindow(Conversations(self.root/'conversations'),JobStore(self.root/'jobs'),autoload=False,model_first=False);self.w.new_task();self.w.show();self.app.processEvents()
        self.w.current['settings']['output_root']=str(self.root/'jobs')
    def tearDown(self):self.w.close();self.app.processEvents();self.tmp.cleanup()
    def wait(self):
        deadline=time.monotonic()+5
        while self.w.busy and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertFalse(self.w.busy)
    def test_initial_task_is_chat_without_task_choices(self):self.assertEqual(step(self.w.current),'kind');self.assertFalse(self.w.choices.isVisible());self.assertEqual(self.w.choices_layout.count(),0)
    def test_switching_tasks_restores_their_drafts(self):
        old=self.w.current_id;self.w.composer.setPlainText('first draft');self.w.new_task();self.w.composer.setPlainText('second draft');self.w.select_task(old);self.assertEqual(self.w.composer.toPlainText(),'first draft')
    def test_async_response_belongs_to_original_task(self):
        first=self.w.current;self.w.model_ready=True;fake=Mock();fake.running=True
        fake.converse.side_effect=lambda *a:(time.sleep(.15) or (Plan('segment',{},'Let us segment your images.'),{'center_mode':'unchanged','row_scope':'unchanged','accept_defaults':False},{'seconds':.15}))
        with patch.object(self.w,'model',fake):
            self.w.composer.setPlainText('Segment images.');self.w.send();self.w.new_task();identity=self.w.current_id;self.wait()
        self.assertEqual(self.w.current_id,identity);self.assertEqual(first['kind'],'segment');self.assertIsNone(self.w.current['kind'])
    def test_file_inspection_callback_does_not_switch_tasks(self):
        old=self.w.current;choose_kind(old,'segment');set_source(old,'image_folder','D:/chosen')
        with patch('assistant_lab.chat_window.inspect_source',side_effect=lambda *a:(time.sleep(.15) or {'images':12})):
            self.w.inspect(old,'image_folder','D:/chosen');self.w.new_task();identity=self.w.current_id;self.wait()
        self.assertEqual(self.w.current_id,identity);self.assertIn('image_folder',old['done']);self.assertNotIn('image_folder',self.w.current['done'])
    def test_plan_never_starts_until_explicit_start(self):
        t=self.w.current;choose_kind(t,'segment');set_source(t,'image_folder','D:/chosen');accept_source(t,'image_folder','D:/chosen',{'images':12})
        with patch.object(self.w.store,'submit') as submit:
            self.w.choose('prompt:particle');self.w.choose('limit:2');self.assertEqual(step(t),'ready');submit.assert_not_called()
    def test_running_task_retains_its_conversation_on_switch(self):
        old=self.w.current;old['state']='running';self.w.new_task();self.assertEqual(old['state'],'running');self.assertNotEqual(self.w.current_id,old['id'])
    def test_prepare_completion_continues_training_conversation(self):
        t=self.w.current;t.update(sourced('train'));t['id']=self.w.current_id;t['state']='running';folder=self.root/'jobs/prepared';folder.mkdir();t['jobs']=[{'id':'prepared','job_dir':str(folder),'action':'prepare_dataset','reported':False}]
        atomic_json(folder/'job_status.json',dict(state='succeeded',result={'dataset':'D:/split'},output='D:/result'))
        self.w.poll();self.assertEqual(t['settings']['dataset'],'D:/split');self.assertEqual(step(t),'ready');self.assertEqual(t['state'],'draft');self.assertTrue(t['jobs'][0]['reported'])
    def test_chosen_output_parent_gets_its_own_worker_registry(self):
        t=self.w.current;identity=t['id'];t.update(sourced('segment'));t['id']=identity;mark(t,'prompt','limit');target=self.root/'selected_output';t['settings']['output_root']=str(target)
        fake={'id':'owned','job_dir':str(target/'owned'),'action':'segment'}
        with patch('assistant_lab.chat_window.JobStore.submit',return_value=fake) as submit:self.w.start_task(t)
        self.assertEqual(t['state'],'running');self.assertEqual(submit.call_args.args[1]['output_root'],str(target));self.assertIn(str(target.resolve()),self.w.stores)
    def test_stop_targets_only_the_selected_conversations_job(self):
        t=self.w.current;folder=self.root/'jobs/owned';folder.mkdir();atomic_json(folder/'job.json',{'id':'owned'});t['jobs']=[{'id':'owned','job_dir':str(folder),'action':'segment','reported':False}];t['state']='running'
        other=self.root/'other_jobs/unrelated';other.mkdir(parents=True);atomic_json(other/'job.json',{'id':'unrelated'})
        self.w.stop_task(t);self.assertTrue((folder/'CANCEL').is_file());self.assertFalse((other/'CANCEL').exists());self.assertEqual(t['state'],'stopping')

if __name__=='__main__':unittest.main()
