from __future__ import annotations
from pathlib import Path
import copy,html,json,time
from PySide6.QtCore import Qt,QThread,Signal,QTimer,QUrl,QPropertyAnimation,QEasingCurve,QAbstractAnimation,QEvent
from PySide6.QtGui import QIcon,QDesktopServices
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
 QListWidget,QListWidgetItem,QSplitter,QScrollArea,QPlainTextEdit,QMenu,QFileDialog,
 QInputDialog,QDialog,QDialogButtonBox,QSizePolicy,QFrame,QMessageBox)
from .config import STATE_ROOT,ROOT,MODEL,DEFAULTS,MODEL_PROFILES,DEFAULT_PROFILE,load_preferences,save_preferences
from .conversations import (Conversations,TITLES,choose_kind,step,question,message,mark,action,review,
 apply_response,set_source,inspect_source,accept_source,PATHS)
from .chat_model import ChatModel
from .protocol import Plan
from .jobs import JobStore,read_json
from .chat_flow import (say,chinese,execution_intent,bind_paths,apply_defaults,guidance,ready_step,
 source_field,resolve_source,activity,finish_activity,find_entry)
from .results import query_type,answer_result,result_context
from .quick_replies import quick_reply,greeting_sticker
from .visual_assets import APP_ICON,sticker_pixmap
from .telegram_ui import TelegramController
from .task_recovery import recover_task
from .reconstruction_sop import ReconstructionSOP
from bl62_theme import ThemeController

def control_input(text):
    return text.lower().strip(' .!。！') in ('stop','safe stop','cancel task','stop the task','停止','停下','停止任务','cancel','pause','取消','暂停','status','progress','进度')

STYLE='''QWidget{background:#101720;color:#e7edf4;font-family:Segoe UI;font-size:14px}
QWidget#sidebar{background:#151e29} QLabel#brand{font-size:20px;font-weight:700}
QWidget#sidebar QLabel{background:transparent}
QLabel#heading{font-size:21px;font-weight:600} QLabel#muted{color:#8d9cad;font-size:12px}
QListWidget{background:transparent;border:0;outline:0;padding:4px} QListWidget::item{padding:15px 10px;margin:3px;border-radius:8px;color:#acbacb}
QListWidget::item:selected{background:#243c40;color:#e9fff7} QListWidget::item:hover{background:#202e3a}
QPushButton{background:#20303f;border:1px solid #344754;border-radius:8px;padding:9px 14px}
QPushButton:hover{background:#2b404b;border-color:#559980} QPushButton:disabled{color:#62717e;border-color:#27313d}
QPushButton#primary{background:#277760;border-color:#37876f;color:white} QPushButton#new{background:#254d43;border-color:#3d7463}
QPlainTextEdit{background:#1b2733;border:1px solid #3a4c5b;border-radius:12px;padding:10px;font-size:15px;selection-background-color:#356957}
QScrollArea{border:0} QScrollBar:vertical{background:#101720;width:10px;margin:3px} QScrollBar::handle:vertical{background:#3c4c5a;border-radius:4px;min-height:35px}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
QFrame#assistantBubble{background:#1a2631;border:1px solid #2a3a47;border-radius:12px}
QFrame#userBubble{background:#22473e;border:1px solid #356355;border-radius:12px}
QFrame#assistantBubble QLabel,QFrame#userBubble QLabel{background:transparent}
QSplitter::handle{background:#283541} QMenu{border:1px solid #3a4c5b;padding:5px} QMenu::item{padding:8px 20px} QMenu::item:selected{background:#315b4e}'''

LIGHT_CHAT='''QWidget{font-size:14px} QWidget#sidebar{background:#f1f4f7}
QLabel#brand{font-size:20px;font-weight:700} QLabel#heading{font-size:21px;font-weight:600}
QLabel#muted{color:#536476;font-size:12px}
QListWidget{background:transparent;border:0;outline:0;padding:4px}
QListWidget::item{padding:15px 10px;margin:3px;border-radius:8px;color:#334155}
QListWidget::item:selected{background:#dbeafe;color:#1e40af}
QListWidget::item:hover{background:#e3eaf2}
QPlainTextEdit{background:#ffffff;border:1px solid #c8d2dc;border-radius:12px;padding:10px;font-size:15px}
QFrame#assistantBubble{background:#ffffff;border:1px solid #ccd6e0;border-radius:12px}
QFrame#userBubble{background:#e7efff;border:1px solid #b8cef7;border-radius:12px}
QFrame#assistantBubble QLabel,QFrame#userBubble QLabel{background:transparent}
'''

class CallThread(QThread):
    done=Signal(object);failed=Signal(str)
    def __init__(self,call,parent):super().__init__(parent);self.call=call
    def run(self):
        try:self.done.emit(self.call())
        except Exception as e:self.failed.emit(str(e))

class Composer(QPlainTextEdit):
    send=Signal()
    def keyPressEvent(self,e):
        if e.key() in (Qt.Key_Return,Qt.Key_Enter) and not e.modifiers() & Qt.ShiftModifier:self.send.emit();e.accept()
        else:super().keyPressEvent(e)

class MessageView(QWidget):
    def __init__(self,entry,parent=None):
        super().__init__(parent);layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);user=entry['role']=='user'
        frame=QFrame();frame.setObjectName('userBubble' if user else 'assistantBubble');frame.setMaximumWidth(820 if not user else 650)
        body=QVBoxLayout(frame);body.setContentsMargins(16,12,16,14)
        who=QLabel('YOU' if user else 'MomoBot');who.setObjectName('muted');body.addWidget(who)
        self.text=QLabel();self.text.setTextFormat(Qt.PlainText);self.text.setWordWrap(True);self.text.setTextInteractionFlags(Qt.TextSelectableByMouse);body.addWidget(self.text)
        self.sticker=QLabel();self.sticker.setAccessibleName('MomoBot kitten greeting');body.addWidget(self.sticker,0,Qt.AlignLeft)
        self.process=QLabel();self.process.setWordWrap(True);self.process.setObjectName('muted');self.process.setTextFormat(Qt.PlainText)
        body.addWidget(self.process)
        if user:layout.addStretch(1)
        layout.addWidget(frame,1)
        self.signature=None;self.update_entry(entry)
    def update_entry(self,entry):
        signature=json.dumps(entry,ensure_ascii=False,sort_keys=True)
        if signature==self.signature:return
        self.signature=signature;self.text.setText(entry['text']);self.text.setVisible(bool(entry['text']))
        pixmap=sticker_pixmap(entry.get('sticker')) if entry['role']=='assistant' else None
        if pixmap is not None and not pixmap.isNull():self.sticker.setPixmap(pixmap);self.sticker.show()
        else:self.sticker.clear();self.sticker.hide()
        events=entry.get('activity',[]);p=entry.get('progress',{})
        working=p.get('state')=='working' and bool(events)
        self.process.setText(events[-1]['text'] if working else '')
        self.process.setVisible(working)

class ChatWindow(QMainWindow):
    def __init__(self,conversations=None,jobs=None,autoload=True):
        super().__init__();self.setWindowTitle('MomoBot');self.resize(1280,900);self.setMinimumSize(900,640)
        self.setWindowIcon(QIcon(str(APP_ICON)));self.setStyleSheet(STYLE)
        self.repo=conversations or Conversations();self.tasks={t['id']:t for t in self.repo.all()};self.store=jobs or JobStore()
        for t in self.tasks.values():
            previous=json.dumps(t,ensure_ascii=False,sort_keys=True)
            t['settings']={**DEFAULTS,**t['settings']}
            records=result_context(t)
            saved_gpu=t['settings']['gpu']
            recover_task(t,records)
            if t.get('sop',{}).get('enabled'):t['settings']['gpu']=saved_gpu
            if previous!=json.dumps(t,ensure_ascii=False,sort_keys=True):self.repo.save(t)
        self.stores={str(self.store.root.resolve()):self.store}
        for t in self.tasks.values():
            for job in t['jobs']:self.store_for(Path(job['job_dir']).parent)
        self.sop=ReconstructionSOP(self)
        for task in self.tasks.values():self.sop.restore(task)
        self.current_id=None;self.model=ChatModel();self.busy=False;self.threads=[];self.model_ready=False;self.progress_key=None
        self.default_gpu=0;self.closing=False
        self.model_profile=load_preferences().get('model_profile',DEFAULT_PROFILE)
        if self.model_profile not in MODEL_PROFILES:self.model_profile=DEFAULT_PROFILE
        self.rendered_id=None;self.views={};self.rendered_order=[];self.scroll_positions={};self.scroll_generation=0
        central=QWidget();outer=QHBoxLayout(central);outer.setContentsMargins(0,0,0,0);split=QSplitter();outer.addWidget(split)
        left=QWidget();left.setObjectName('sidebar');left.setMinimumWidth(220);left.setMaximumWidth(360);lv=QVBoxLayout(left);lv.setContentsMargins(15,24,15,16)
        brand=QLabel('MomoBot');brand.setObjectName('brand');lv.addWidget(brand)
        label=QLabel('TASKS');label.setObjectName('muted');lv.addWidget(label);lv.addSpacing(10)
        self.new_btn=QPushButton('+  New task');self.new_btn.setObjectName('new');self.new_btn.clicked.connect(self.new_task);lv.addWidget(self.new_btn)
        self.task_list=QListWidget();self.task_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.task_list.setWordWrap(False);self.task_list.setTextElideMode(Qt.ElideRight);self.task_list.currentItemChanged.connect(self.selected);self.task_list.itemDoubleClicked.connect(self.rename_task);lv.addWidget(self.task_list,1)
        self.task_list.setContextMenuPolicy(Qt.CustomContextMenu);self.task_list.customContextMenuRequested.connect(self.task_context_menu)
        self.delete_btn=QPushButton('Delete task');self.delete_btn.clicked.connect(lambda:self.delete_task());lv.addWidget(self.delete_btn)
        local=QLabel('Local model · Saved on this computer');local.setObjectName('muted');local.setWordWrap(True);lv.addWidget(local);split.addWidget(left)
        right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(24,22,24,18);rv.setSpacing(14)
        head=QHBoxLayout();self.heading=QLabel('New task');self.heading.setObjectName('heading');head.addWidget(self.heading,1)
        self.model_status=QLabel('Loading local model…' if autoload else 'Model not loaded');self.model_status.setObjectName('muted');head.addWidget(self.model_status)
        self.more_btn=QPushButton('Settings');self.more_btn.setFixedWidth(100);self.more_btn.clicked.connect(self.more);head.addWidget(self.more_btn)
        self.theme_button=QPushButton('Switch to Light');head.addWidget(self.theme_button);rv.addLayout(head)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.messages_widget=QWidget();self.messages_layout=QVBoxLayout(self.messages_widget);self.messages_layout.setContentsMargins(0,8,8,8);self.messages_layout.setSpacing(16);self.messages_layout.addStretch(1);self.scroll.setWidget(self.messages_widget);rv.addWidget(self.scroll,1)
        self.scroll_animation=QPropertyAnimation(self.scroll.verticalScrollBar(),b'value',self);self.scroll_animation.setDuration(160);self.scroll_animation.setEasingCurve(QEasingCurve.OutCubic);self.scroll.viewport().installEventFilter(self)
        self.scroll.verticalScrollBar().installEventFilter(self)
        self.choices=QWidget();self.choices_layout=QVBoxLayout(self.choices);self.choices_layout.setContentsMargins(0,0,0,0);self.choices_layout.setSpacing(8);rv.addWidget(self.choices)
        compose=QHBoxLayout();self.attach_btn=QPushButton('+');self.attach_btn.setFixedWidth(43);self.attach_btn.setToolTip('Choose an input file or folder');self.attach_btn.clicked.connect(self.attach_menu);compose.addWidget(self.attach_btn,0,Qt.AlignBottom)
        self.composer=Composer();self.composer.setPlaceholderText('Message MomoBot…');self.composer.setFixedHeight(88);self.composer.send.connect(self.send);compose.addWidget(self.composer,1)
        self.send_btn=QPushButton('Send');self.send_btn.setObjectName('primary');self.send_btn.clicked.connect(self.send);compose.addWidget(self.send_btn,0,Qt.AlignBottom);rv.addLayout(compose)
        self.composer.textChanged.connect(self.update_send_enabled)
        self.footer=QLabel('Enter to send · Shift + Enter for a new line');self.footer.setObjectName('muted');rv.addWidget(self.footer)
        split.addWidget(right);split.setSizes([260,1020]);self.setCentralWidget(central)
        self.timer=QTimer(self);self.timer.setInterval(800);self.timer.timeout.connect(self.poll);self.timer.start()
        for store in self.stores.values():store.active()
        if not self.tasks and not self.repo.allows_empty():self.new_task()
        elif not self.tasks:self.render()
        else:self.refresh_list();self.select_task(next(iter(self.tasks)))
        self.poll()
        if autoload:QTimer.singleShot(200,self.load_model)
        self.telegram=TelegramController(self,autoload=autoload)
        self.theme_manager=ThemeController(self,self.theme_button,'MomoBot',STYLE,extra_light=LIGHT_CHAT,changed=self._theme_changed)

    def _theme_changed(self,mode):
        if self.telegram.dialog:self.telegram.dialog.apply_theme()

    @property
    def current(self):return self.tasks.get(self.current_id)
    def store_for(self,root):
        key=str(Path(root).resolve())
        if key not in self.stores:self.stores[key]=JobStore(root)
        return self.stores[key]
    def save(self,task):self.repo.save(task)
    def add(self,task,role,text,sticker=None):message(task,role,text,sticker=sticker);self.save(task)
    def new_task(self):
        if self.current:self.current['draft']=self.composer.toPlainText();self.save(self.current)
        task=self.repo.create();task['settings']['gpu']=self.default_gpu;self.tasks={task['id']:task,**self.tasks};self.save(task);self.refresh_list();self.select_task(task['id'])
    def refresh_list(self):
        self.task_list.blockSignals(True);self.task_list.clear()
        for task in self.tasks.values():
            state={'draft':'Draft','running':'Running','stopping':'Stopping','completed':'Completed','failed':'Needs attention'}.get(task['state'],task['state'])
            item=QListWidgetItem(task['title']+'\n'+state);item.setData(Qt.UserRole,task['id']);item.setToolTip(task['title']);self.task_list.addItem(item)
            if task['id']==self.current_id:self.task_list.setCurrentItem(item)
        self.task_list.blockSignals(False)
    def select_task(self,identity):
        if self.current and self.current_id!=identity:self.current['draft']=self.composer.toPlainText();self.save(self.current);self.scroll_positions[self.current_id]=self.scroll.verticalScrollBar().value()
        self.current_id=identity;self.composer.setPlainText(self.current.get('draft',''));self.refresh_list();self.render()
    def selected(self,item,previous):
        if item:self.select_task(item.data(Qt.UserRole))
    def rename_task(self,item):
        task=self.tasks[item.data(Qt.UserRole)];name,ok=QInputDialog.getText(self,'Rename task','Name',text=task['title'])
        if ok and name.strip():task['title']=name.strip()[:120];self.save(task);self.refresh_list();self.render()
    def task_context_menu(self,position):
        item=self.task_list.itemAt(position)
        if not item:return
        identity=item.data(Qt.UserRole);menu=QMenu(self)
        rename=menu.addAction('Rename task');rename.triggered.connect(lambda:self.rename_task(item))
        delete=menu.addAction('Delete task…')
        delete.triggered.connect(lambda:self.delete_task(identity))
        menu.exec(self.task_list.viewport().mapToGlobal(position))
    def _task_delete_blocked(self,task):
        if task['state'] in ('running','stopping'):return 'Use Safe Stop and wait for this task to stop before deleting it.'
        for job in task['jobs']:
            status=read_json(Path(job['job_dir'])/'job_status.json')
            if status.get('state') in ('queued','running','stopping'):
                return 'Use Safe Stop and wait for this task to stop before deleting it.'
        return ''
    def delete_task(self,identity=None):
        identity=identity or self.current_id;task=self.tasks.get(identity)
        if task is None:return False
        blocked=self._task_delete_blocked(task)
        if blocked:QMessageBox.information(self,'Delete task',blocked);return False
        answer=QMessageBox.question(self,'Delete task',f'Delete "{task["title"]}" and its chat history?\n\nGenerated results and source data will be kept.',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return False
        # Timers and remote requests can run while the confirmation dialog is open.
        blocked=self._task_delete_blocked(task)
        if blocked:QMessageBox.information(self,'Delete task',blocked);return False
        try:self.repo.delete(identity)
        except OSError as error:
            QMessageBox.warning(self,'Cannot delete task',str(error));return False
        task.update(_deleted=True,cancel_requested=True,run_requested=False)
        del self.tasks[identity];self.scroll_positions.pop(identity,None)
        if self.current_id==identity:
            self.current_id=None;self.composer.clear()
            if self.tasks:self.select_task(next(iter(self.tasks)))
            else:self.refresh_list();self.render()
        else:self.refresh_list()
        notice='Task deleted. Results kept.'
        try:self.telegram.forget_task(identity)
        except OSError:notice='Task deleted. Telegram task settings could not be updated.'
        self.statusBar().showMessage(notice,10000);return True
    def clear_layout(self,layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
            elif item.layout():self.clear_layout(item.layout())
    def render(self,scroll_bottom=True):
        task=self.current
        if not task:
            self.scroll_animation.stop();self.clear_layout(self.messages_layout);self.messages_layout.addStretch(1)
            self.views={};self.rendered_order=[];self.rendered_id=None;self.heading.setText('New task')
            self.composer.clear();self.composer.setPlaceholderText('Create a new task to begin…')
            self.clear_layout(self.choices_layout);self.choices.hide();self.update_send_enabled();return
        self.composer.setPlaceholderText('Message MomoBot…')
        self.update_send_enabled()
        bar=self.scroll.verticalScrollBar();position=bar.value();follow=bar.maximum()-position<60 or self.scroll_animation.state()==QAbstractAnimation.Running
        switched=self.rendered_id!=task['id'];order=[m['id'] for m in task['messages']]
        if switched or order[:len(self.rendered_order)]!=self.rendered_order:
            self.scroll_animation.stop();self.clear_layout(self.messages_layout);self.messages_layout.addStretch(1);self.views={};self.rendered_order=[];self.rendered_id=task['id']
        self.heading.setText(task['title']);self.heading.setToolTip(task['title'])
        for entry in task['messages']:
            if entry['id'] not in self.views:
                view=MessageView(entry);self.views[entry['id']]=view;self.messages_layout.addWidget(view)
            else:self.views[entry['id']].update_entry(entry)
        self.rendered_order=order;self.render_choices();self.update_progress();self.scroll_generation+=1;generation=self.scroll_generation
        def settle():
            if self.current_id!=task['id'] or generation!=self.scroll_generation:return
            self.messages_layout.activate()
            if switched:bar.setValue(self.scroll_positions.get(task['id'],bar.maximum()))
            elif follow and scroll_bottom:
                self.scroll_animation.stop();self.scroll_animation.setStartValue(bar.value());self.scroll_animation.setEndValue(bar.maximum());self.scroll_animation.start()
            else:bar.setValue(position)
        QTimer.singleShot(0,settle)
    def eventFilter(self,obj,event):
        if obj in (self.scroll.viewport(),self.scroll.verticalScrollBar()) and event.type() in (QEvent.Wheel,QEvent.MouseButtonPress,QEvent.KeyPress):self.scroll_animation.stop()
        return super().eventFilter(obj,event)
    def render_choices(self):
        self.clear_layout(self.choices_layout);self.choices.setVisible(False)
    def guide(self,task):
        text=guidance(task)
        if text and text!=task.get('last_question'):
            task['last_question']=text;message(task,'assistant',text)
        self.save(task);self.refresh_list()
        if self.current_id==task['id']:self.render()
    def fail(self,identity,error):
        task=self.tasks.get(identity)
        if task is None:return
        reply=task.get('reply_id');entry=find_entry(task,reply)
        if entry:
            entry['text']=say(task,'I could not complete that step. ','这一步没有完成：')+error;activity(task,reply,say(task,'The request stopped with an error.','请求遇到错误，已停止。'),'error');finish_activity(task,reply,'error');self.save(task)
        else:self.add(task,'assistant','I could not complete that step. '+error)
        if self.current_id==identity:self.render()
    def background(self,call,done,identity=None):
        if self.busy:return False
        self.busy=True;self.update_send_enabled();self.attach_btn.setEnabled(False);self.model_status.setText('Working…');self.render_choices()
        thread=CallThread(call,self);self.threads.append(thread)
        def success(value):
            if identity is not None and identity not in self.tasks:return
            try:done(value)
            except Exception as e:self.fail(identity or self.current_id,str(e))
        thread.done.connect(success);thread.failed.connect(lambda error:self.fail(identity or self.current_id,error))
        def finished():
            self.busy=False;self.update_send_enabled();self.model_status.setText(MODEL_PROFILES[self.model_profile]['label']+' · Ready' if self.model_ready and self.model.running else 'Local model not loaded');self.threads.remove(thread);thread.deleteLater();self.render_choices()
        thread.finished.connect(finished);thread.start();return True
    def load_model(self,restart=False):
        if self.busy:return
        if self.model.running and self.model_ready and not restart:return
        profile=MODEL_PROFILES[self.model_profile]
        def load():
            if restart:self.model.stop()
            self.model.start(profile['mode'],threads=8,context=profile['context'],model_path=profile['model_path'],**profile.get('options',{}));self.model.wait_ready(timeout=300)
        def ready(_):self.model_ready=True
        self.model_ready=False
        self.background(load,ready)
        self.model_status.setText('Loading '+profile['label']+'…')
    def select_language_model(self):
        if self.busy:return
        keys=list(MODEL_PROFILES);labels=[MODEL_PROFILES[k]['label'] for k in keys]
        value,ok=QInputDialog.getItem(self,'Language model','Model',labels,keys.index(self.model_profile),False)
        if ok:
            selected=keys[labels.index(value)]
            if not Path(MODEL_PROFILES[selected]['model_path']).is_file():
                QMessageBox.information(self,'Model not installed','Download the selected model first:\n'+str(MODEL_PROFILES[selected]['model_path']));return
            self.model_profile=selected;prefs=load_preferences();prefs['model_profile']=self.model_profile;save_preferences(prefs);self.load_model(restart=True)
    def choose(self,token):
        task=self.current
        if not task:return
        if token=='new':self.new_task();return
        if token=='status':self.show_status(task);return
        if token=='stop':self.stop_task(task);return
        if token=='open_output':self.open_output(task);return
        if self.busy:return
        if token=='run':self.start_task(task);return
        if token=='revise':task['state']='draft';task['last_question']=None;self.guide(task);return
        if token.startswith(('browse:','json:')):
            mode,field=token.split(':',1);self.browse(field,mode=='json');return
        label=next((label for label,key in question(task)[1] if key==token),token)
        self.add(task,'user',label)
        if token.startswith('kind:'):choose_kind(task,token.split(':',1)[1])
        elif token.startswith('center:'):task['center_mode']=token.split(':',1)[1]
        elif token.startswith('rows:'):apply_response(task,Plan('set_parameters',{},''),row_scope=token.split(':',1)[1])
        elif token.startswith('prompt:'):apply_response(task,Plan('set_parameters',{'prompt':token.split(':',1)[1]},''))
        elif token.startswith('limit:'):apply_response(task,Plan('set_parameters',{'max_images':0 if token.endswith('all') else 2},''))
        elif token.startswith('split:'):apply_response(task,Plan('set_parameters',{'train_percent':int(token.split(':',1)[1])},''))
        elif token.startswith('epochs:'):apply_response(task,Plan('set_parameters',{'epochs':int(token.split(':',1)[1])},''))
        self.guide(task)
    def attach_menu(self):
        if self.busy or not self.current:return
        menu=QMenu(self)
        for label,field,json_file in [('HDF5 data','input_hdf5',False),('Image folder','image_folder',False),('Dataset folder','dataset',False),('COCO JSON file','dataset',True),('SAM3 checkpoint','checkpoint',False)]:
            a=menu.addAction(label);a.triggered.connect(lambda checked=False,f=field,j=json_file:self.browse(f,j))
        menu.exec(self.attach_btn.mapToGlobal(self.attach_btn.rect().topLeft()))
    def browse(self,field,json_file=False):
        task=self.current
        if task['state'] in ('running','stopping'):self.fail(task['id'],'Wait for the active task before changing its files.');return
        expected='image_folder' if task['kind']=='segment' else 'dataset' if task['kind'] in ('train','prepare_dataset') else 'input_hdf5'
        if task['kind'] and field not in (expected,'checkpoint','resume_checkpoint','output_root'):
            self.fail(task['id'],'This input belongs to another task type. Create a new task for it.');return
        if field in ('image_folder','output_root') or field=='dataset' and not json_file:value=QFileDialog.getExistingDirectory(self,'Choose folder',task['settings'].get(field,''))
        else:
            filter_='COCO JSON (*.json)' if json_file else 'HDF5 (*.h5 *.hdf5 *.hdf)' if field=='input_hdf5' else 'Checkpoint (*.pt *.pth)'
            value=QFileDialog.getOpenFileName(self,'Choose file',task['settings'].get(field,''),filter_)[0]
        if not value:return
        if not task['kind'] and field in ('input_hdf5','image_folder','dataset'):choose_kind(task,{'input_hdf5':'reconstruct','image_folder':'segment','dataset':'train'}[field])
        if not task['kind']:self.fail(task['id'],'Choose a task first.');return
        set_source(task,field,value);self.add(task,'user',('Output folder: ' if field=='output_root' else 'Selected: ')+value)
        if field=='output_root':self.guide(task);return
        self.inspect(task,field,value)
    def inspect(self,task,field,value,remaining=None):
        identity=task['id'];reply=task.get('reply_id')
        activity(task,reply,say(task,'Checking input path and reading metadata','检查输入路径并读取数据信息'));self.render_if_current(task)
        def read():
            resolved=resolve_source(field,value);return resolved,inspect_source(field,resolved)
        def done(meta):
            resolved,metadata=meta
            if task['settings'].get(field)!=value:return
            task['settings'][field]=resolved
            if accept_source(task,field,resolved,metadata):
                details=say(task,'Input verified','输入已确认')
                if field=='input_hdf5':details=say(task,f"Read {metadata['projections']} projections · {metadata['rows']} rows · width {metadata['width']}",f"已读取 {metadata['projections']} 个投影、{metadata['rows']} 层，图像宽度 {metadata['width']}")
                elif field=='image_folder':details=say(task,f"Found {metadata['images']} images",f"找到 {metadata['images']} 张图片")
                activity(task,reply,details,'done');self.save(task);self.render_if_current(task)
            QTimer.singleShot(50,lambda:self.advance(task,reply))
        self.background(read,done,identity)
    def render_if_current(self,task):
        if self.current_id==task['id']:self.render()
    def advance(self,task,reply):
        if self.closing or task.get('_deleted') or task['id'] not in self.tasks:return
        if self.busy:QTimer.singleShot(50,lambda:self.advance(task,reply));return
        if self.sop.guard_advance(task):return
        if task.get('cancel_requested'):
            entry=find_entry(task,reply)
            if entry:entry['text']=say(task,'Request cancelled before execution.','请求已取消，未开始执行。');finish_activity(task,reply)
            task['run_requested']=False;self.save(task);self.render_if_current(task);return
        apply_defaults(task)
        if task['kind']:
            field=source_field(task);value=task['settings'][field]
            if value and field not in task['done']:self.inspect(task,field,value);return
            for field in ('checkpoint','resume_checkpoint'):
                if task['settings'].get(field) and field not in task['done']:
                    if not Path(task['settings'][field]).is_file():self.fail(task['id'],'Checkpoint file does not exist: '+task['settings'][field]);return
                    mark(task,field)
        current=ready_step(task);entry=find_entry(task,reply)
        if current=='ready' and task.get('run_requested'):
            self.start_task(task,reply);return
        text=guidance(task)
        if entry:
            if text not in entry['text']:entry['text']=(entry['text']+'\n\n'+text).strip()
            finish_activity(task,reply)
        else:self.add(task,'assistant',text)
        task['awaiting_confirmation']=current=='ready';self.save(task);self.refresh_list();self.render_if_current(task)
    def send(self):
        text=self.composer.toPlainText().strip();task=self.current
        if not text or not task:return
        if self.busy and quick_reply(text) is None and not control_input(text):return
        self.composer.clear();task['draft']=''
        self.submit_text(task,text)
    def submit_text(self,task,text,remote=False):
        if not task or task.get('_deleted'):return
        instant=quick_reply(text)
        control_text=text.lower().strip(' .!。！')
        busy_control=control_text in ('stop','safe stop','cancel task','stop the task','停止','停下','停止任务','cancel','pause','取消','暂停','status','progress','进度')
        if self.closing or not text.strip() or self.busy and instant is None and not busy_control:return
        if chinese(text):task['language']='zh'
        elif len(text.split())>=3 and not (':' in text and '\\' in text):task['language']='en'
        self.add(task,'user',text)
        if instant is not None:
            self.add(task,'assistant',instant,sticker=greeting_sticker(text));self.render();return
        task['cancel_requested']=False
        lowered=text.lower().strip('.! ')
        if lowered in ('stop','safe stop','cancel task','stop the task','停止','停下','停止任务'):self.stop_task(task);return
        if lowered in ('status','progress','show progress','进度','现在怎么样了'):self.show_status(task);return
        request=execution_intent(text,task.get('awaiting_confirmation',False))
        query=query_type(text)
        if query=='time' and self.sop.enabled(task) and task['sop'].get('phase')=='confirm':
            from .reconstruction_sop import estimate
            self.sop.tell(task,estimate(task));return
        if query and not request and (task['jobs'] or query.startswith('open_') or __import__('re').search(r'result|结果|did.*find|already.*search',lowered)):
            self.add(task,'assistant','');rid=task['messages'][-1]['id'];task['reply_id']=rid
            activity(task,rid,say(task,'Reading the saved task results','正在读取已保存的任务结果'));self.render()
            def result_ready(value):
                answer,path=value;find_entry(task,rid)['text']=answer;finish_activity(task,rid);self.save(task);self.render_if_current(task)
                if path:
                    if remote and self.telegram.bridge and Path(path).is_file():self.telegram.bridge.send_image(path)
                    elif not remote:QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            self.background(lambda:answer_result(task,query),result_ready,task['id']);return
        try:
            if self.sop.handle(task,text,remote):return
        except (ValueError,OSError) as error:
            self.sop.reject(task,error);return
        if task['jobs'] and __import__('re').search(r'result.*(?:correct|right)|looks correct|结果.*(?:是对的|正确|没问题)|这个是正确答案',text.lower()) and '?' not in text and '？' not in text:
            task['jobs'][-1]['user_review']={'status':'accepted','message':text,'time':__import__('datetime').datetime.now().isoformat()};self.save(task)
        if request and lowered in ('start','run','go ahead','yes','ok','okay','开始','开始吧','执行','运行','确认','好的','可以') and task['kind']:
            task['run_requested']=True
            if task['state']=='completed':task['state']='draft'
            self.add(task,'assistant','');task['reply_id']=task['messages'][-1]['id'];self.advance(task,task['reply_id']);return
        if not self.model_ready or not self.model.running:
            self.add(task,'assistant',say(task,'The local model is still loading. Please send your message again when it is ready.','本地模型还在加载，准备好后再发送一次即可。'));self.render();return
        self.add(task,'assistant','');reply=task['messages'][-1]['id'];task['reply_id']=reply
        activity(task,reply,say(task,'Understanding your request with the local model','本地模型正在理解你的请求'));self.render()
        captured=copy.deepcopy(task);identity=task['id']
        def done(result):
            if task.get('cancel_requested'):
                find_entry(task,reply)['text']=say(task,'Request cancelled before execution.','请求已取消，未开始执行。');finish_activity(task,reply);self.save(task);self.render_if_current(task);return
            plan,control,meta=result
            if self.sop.enabled(task):
                entry=find_entry(task,reply);entry['text']=plan.message;finish_activity(task,reply);self.save(task);self.render_if_current(task);return
            low=text.lower().strip(' .!。！');current=ready_step(task)
            if request and __import__('re').search(r'\b(trial|sweep|jitter)\b|抖动|试重建|自己挑|自己选',low):
                plan.action='try_angle' if __import__('re').search(r'lamino.*angle|angle.*lamino|角度',low) else 'try_center';control['center_mode']='unchanged'
            if current=='search_mode' and low in ('auto','automatic','sam3','自动','自动找','用sam3','自动评分'):
                task['search_mode']='auto';plan.action='set_parameters';control['center_mode']='auto'
            elif current=='search_mode' and low in ('manual','trial','sweep','抖动','试重建','手动挑'):
                plan.action='try_center';plan.updates={};control['center_mode']='unchanged'
            if not meta.get('unsupported_capability') and current=='prompt' and __import__('re').fullmatch(r'[A-Za-z][A-Za-z -]{0,50}',text) and not __import__('re').match(r'^(what|why|how|explain)\b',low):
                plan.action='set_parameters';plan.updates['prompt']=task['settings']['prompt'] if low in ('default','use default','use the default') else text
            if plan.action=='stop':finish_activity(task,reply);self.stop_task(task);return
            if plan.action=='status':finish_activity(task,reply);self.show_status(task);return
            if plan.action=='open_output':
                finish_activity(task,reply)
                if remote:
                    find_entry(task,reply)['text']=answer_result(task,'output')[0];self.save(task);self.render_if_current(task)
                else:self.open_output(task)
                return
            if plan.action in ('help','clarify'):
                entry=find_entry(task,reply);entry['text']=plan.message;task['awaiting_confirmation']=False;finish_activity(task,reply);self.save(task);self.render_if_current(task);return
            target=task;rid=reply
            if plan.action in TITLES and task['kind'] and plan.action!=task['kind']:
                if task['state'] in ('running','stopping'):
                    target=self.repo.create();target['language']=task.get('language','en');self.tasks={target['id']:target,**self.tasks};self.refresh_list()
                    self.add(target,'user',text);self.add(target,'assistant','');rid=target['messages'][-1]['id'];target['reply_id']=rid
                    find_entry(task,reply)['text']=say(task,'I created another task for this request.','我为这个请求创建了另一个任务。');finish_activity(task,reply);self.save(task)
                    if remote:self.telegram.subscribe(target,False)
                    elif self.current_id==identity:self.select_task(target['id'])
                else:choose_kind(target,plan.action);target['state']='draft'
            if target['kind'] is None and plan.action in TITLES:choose_kind(target,plan.action)
            bind_paths(target,plan,text);low=text.lower()
            if target['kind']=='find_center' and ('auto' in low or 'sam3' in low or '自动' in text):target['search_mode']='auto'
            if ready_step(target)=='prompt' and not plan.updates.get('prompt') and __import__('re').fullmatch(r'[A-Za-z][A-Za-z -]{0,50}',text):plan.updates['prompt']=text
            if target['kind']=='try_angle':
                target['settings'].update(geometry='laminography',method='linerec')
                if not target.get('trial_defaults_set'):target['settings'].update(trial_width=2.,trial_step=.25);target['trial_defaults_set']=True
            scope=control['row_scope']
            if target['kind'] in ('reconstruct','analyze') and __import__('re').search(r'\bfull\s+volume\b|\ball\s+(?:slices|rows)\b|重建全部|全部重建',low):scope='all'
            if any(k in plan.updates for k in ('start_row','end_row')):scope='unchanged'
            if scope!='unchanged' and not target['metadata'].get('rows'):target['requested_scope']=scope;scope='unchanged'
            if target['state']=='completed':target['state']='draft'
            draft=copy.deepcopy(target);apply_response(draft,plan,control['center_mode'],scope,control['accept_defaults'])
            target.clear();target.update(draft);target['run_requested']=target.get('run_requested',False) or request
            if not request and __import__('re').search(r"don't|do not|not yet|先不|不要运行|只讨论",low):target['run_requested']=False
            entry=find_entry(target,rid);entry['text']=plan.message
            activity(target,rid,say(target,'Request interpreted; checking task inputs','已理解请求，正在检查任务输入'),'done')
            folder=STATE_ROOT/'outputs/model_traces';folder.mkdir(parents=True,exist_ok=True)
            (folder/f'{time.time_ns()}.json').write_text(json.dumps(dict(task_id=identity,command=text,response=meta),indent=2,ensure_ascii=False),encoding='utf-8')
            self.save(target);self.render_if_current(target);QTimer.singleShot(50,lambda:self.advance(target,rid))
        self.background(lambda:self.model.converse(text,captured),done,identity)

    def update_send_enabled(self):
        self.send_btn.setEnabled(self.current is not None and (not self.busy or quick_reply(self.composer.toPlainText()) is not None or control_input(self.composer.toPlainText())))
        self.attach_btn.setEnabled(self.current is not None and not self.busy)
        self.delete_btn.setEnabled(self.current is not None)

    def start_task(self,task,reply=None):
        if task.get('_deleted') or task['id'] not in self.tasks:return
        if not self.sop.before_start(task):return
        if ready_step(task)!='ready':self.guide(task);return
        try:
            if any(store.active() for store in self.stores.values()):raise ValueError('Another task is running. Open it in the task list, or wait for it to finish.')
            settings=copy.deepcopy(task['settings'])
            store=self.store_for(settings['output_root'])
            job=store.submit(action(task),settings,dict(conversation_id=task['id'],review=review(task)))
            if task['kind']=='train' and job['action']=='prepare_dataset':task['continue_training']=True
            reply=reply or task.get('reply_id')
            task['jobs'].append(dict(id=job['id'],job_dir=job['job_dir'],action=job['action'],reported=False,reply_id=reply,sop_stage=task.get('sop',{}).get('active_stage') if task.get('sop',{}).get('phase')=='dispatch' else None,source_stat=task.get('sop',{}).get('source_stat')));task['state']='running';task['run_requested']=False;task['awaiting_confirmation']=False
            summary=say(task,'Started ','已启动：')+TITLES.get(job['action'],job['action'])
            summary+=f"\nGPU {settings['gpu']} · "+('prompt '+settings['prompt'] if job['action']=='segment' else f"rows [{settings['start_row']}, {settings['end_row']})" if job['action'] in ('reconstruct','analyze') else '')
            if job['action']=='train':summary+=f"\n{settings['epochs']} epoch(s) · batch {settings['batch_size']}"
            if find_entry(task,reply):find_entry(task,reply)['text']=summary;activity(task,reply,say(task,'Scientific worker submitted','已提交实际计算任务'))
            else:self.add(task,'assistant',summary)
            self.save(task);self.refresh_list();self.render_if_current(task)
        except Exception as e:self.fail(task['id'],str(e))
    def latest(self,task):return task['jobs'][-1] if task['jobs'] else None
    def show_status(self,task):
        job=self.latest(task)
        if not job:self.add(task,'assistant',say(task,'No task has started yet. ','尚未开始计算。')+guidance(task))
        else:
            status=read_json(Path(job['job_dir'])/'job_status.json');self.add(task,'assistant',status.get('phase','Queued')+f" · {status.get('elapsed_seconds',0):.0f} s")
        if self.current_id==task['id']:self.render()
    def stop_task(self,task):
        task['cancel_requested']=True;task['run_requested']=False
        if self.sop.enabled(task) and task['sop']['phase']=='reading':
            self.sop.phase(task,'paused');self.add(task,'assistant',say(task,'Cancelled the pending file request. No reconstruction has started.','已取消文件读取请求，尚未开始重建。'));self.render_if_current(task);return
        job=self.latest(task)
        if job and task['state'] in ('running','stopping'):
            self.store_for(Path(job['job_dir']).parent).stop(job);task['state']='stopping';self.add(task,'assistant','Safe Stop requested. Waiting for this task to stop.');self.refresh_list()
        else:self.add(task,'assistant','This conversation has no running task.')
        if self.current_id==task['id']:self.render()
    def open_output(self,task):
        job=self.latest(task)
        if job:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(job['job_dir'])/'results')))
        else:self.fail(task['id'],'There are no results yet.')
    def poll(self):
        changed=False
        for task in self.tasks.values():
            job=self.latest(task)
            if not job or job.get('reported'):continue
            s=read_json(Path(job['job_dir'])/'job_status.json');state=s.get('state')
            reply=job.get('reply_id');entry=find_entry(task,reply)
            if state not in ('succeeded','failed','stopped'):
                if entry and state in ('running','stopping','queued'):
                    old=json.dumps(entry.get('activity',[]))+str(entry.get('progress'))
                    activity(task,reply,s.get('phase','Queued'),'working',s.get('completed',0),s.get('total',0))
                    if old!=json.dumps(entry.get('activity',[]))+str(entry.get('progress')):self.save(task);changed=True
                continue
            job['reported']=True;job['final_state']=state;changed=True
            if self.sop.completed(task,job,s):
                self.save(task);continue
            if state=='succeeded':
                result=s.get('result',{});center=result.get('recommended_center',result.get('center_search',{}).get('recommended_center'))
                if center is not None:task['settings']['center']=float(center);task['center_mode']='known'
                text=say(task,'Completed ','已完成：')+TITLES.get(job['action'],job['action'])
                if center is not None:text+=say(task,f'\nRotation center: {center:g} px',f'\n旋转中心：{center:g} 像素')
                if job['action'] in ('try_center','try_angle'):text+=say(task,f"\nGenerated {result.get('candidates',0)} candidates on slice {result.get('trial_row')}. Compare the images and tell me your chosen value.",f"\n使用第 {result.get('trial_row')} 层生成了 {result.get('candidates',0)} 张候选图。比较图片后，把选中的参数告诉我即可。")
                text+='\n'+say(task,'Results: ','结果目录：')+result.get('folder',s.get('output',''))
                if entry:entry['text']=text;activity(task,reply,say(task,'Results saved and verified','结果已保存并核对'),'done');finish_activity(task,reply)
                else:self.add(task,'assistant',text)
                if job['action']=='prepare_dataset' and task['kind']=='train':
                    task['settings']['dataset']=result['dataset'];task['prepared']=True;task['needs_split']=False;task['state']='draft';task['last_question']=None;mark(task,'dataset')
                    if task.get('continue_training'):
                        task['run_requested']=True;self.add(task,'assistant',say(task,'The dataset is prepared. Starting the requested training.','数据集准备完成，继续执行你要求的训练。'));rid=task['messages'][-1]['id'];task['reply_id']=rid;QTimer.singleShot(50,lambda t=task,r=rid:self.advance(t,r))
                    else:self.guide(task)
                else:task['state']='completed'
            else:
                task['state']='failed';text=('Task stopped. Partial results were kept.' if state=='stopped' else 'The task failed. '+s.get('error','Open the log for details.'))
                if entry:entry['text']=text;finish_activity(task,reply,'error')
                else:self.add(task,'assistant',text)
            self.save(task)
        if changed:self.refresh_list();self.render(scroll_bottom=True)
        self.update_progress()
    def update_progress(self):
        task=self.current;job=self.latest(task) if task else None
        if not job:return
        s=read_json(Path(job['job_dir'])/'job_status.json');state=s.get('state','queued');phase=s.get('phase','Queued');n=s.get('total',0);done=s.get('completed',0)
        temp=Path(job['job_dir'])/'results/experiment/checkpoints/checkpoint.pt.tmp'
        if state=='running' and temp.is_file():phase=f'Saving training checkpoint · {temp.stat().st_size/2**30:.2f} GiB written';n=0
        reply=job.get('reply_id');entry=find_entry(task,reply)
        if entry and state in ('running','queued','stopping'):
            previous=json.dumps(entry.get('activity',[]),ensure_ascii=False)+str(entry.get('progress'))
            activity(task,reply,phase,'working',done,n)
            if previous!=json.dumps(entry.get('activity',[]),ensure_ascii=False)+str(entry.get('progress')):
                self.save(task)
                if reply in self.views:self.views[reply].update_entry(entry)
    def more(self):
        menu=QMenu(self)
        a=menu.addAction('Chat from Anywhere…');a.triggered.connect(self.telegram.show)
        a=menu.addAction('Language model…');a.setEnabled(not self.busy);a.triggered.connect(self.select_language_model)
        a=menu.addAction('Reload local model');a.setEnabled(not self.busy);a.triggered.connect(lambda:self.load_model(restart=True))
        a=menu.addAction('Task GPU…');a.setEnabled(not self.busy and self.current is not None);a.triggered.connect(self.select_gpu)
        a=menu.addAction('View task log');a.setEnabled(self.current is not None);a.triggered.connect(self.show_log)
        a=menu.addAction('Open results');a.setEnabled(self.current is not None);a.triggered.connect(lambda:self.open_output(self.current))
        a=menu.addAction('Delete task…');a.setEnabled(self.current is not None);a.triggered.connect(lambda:self.delete_task())
        menu.addSeparator();a=menu.addAction('About access permissions');a.setEnabled(self.current is not None);a.triggered.connect(self.permissions)
        menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))
    def select_gpu(self):
        if self.current['state'] in ('running','stopping'):self.fail(self.current_id,'Wait for this task before changing its GPU.');return
        value,ok=QInputDialog.getItem(self,'Task GPU','Use GPU',['GPU 0','GPU 1'],self.current['settings']['gpu'],False)
        if ok:
            gpu=int(value.split()[-1]);self.current['settings']['gpu']=gpu;self.default_gpu=gpu;self.add(self.current,'user',value);self.guide(self.current)
    def show_log(self):
        job=self.latest(self.current)
        dialog=QDialog(self);dialog.setWindowTitle('Task log');dialog.resize(900,600);layout=QVBoxLayout(dialog);edit=QPlainTextEdit();edit.setReadOnly(True)
        path=Path(job['job_dir'])/'backend.log' if job else None
        if path and path.exists():
            with path.open('rb') as f:
                if path.stat().st_size>100000:f.seek(-100000,2)
                edit.setPlainText(f.read().decode('utf-8',errors='replace'))
        else:edit.setPlainText('No task log yet.')
        layout.addWidget(edit);buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()
    def permissions(self):
        self.add(self.current,'assistant','The local model can arrange supported reconstruction, trials, center search, segmentation and training tasks. A direct request in chat authorizes the task after input checks; questions and discussions do not execute jobs. It cannot execute arbitrary commands, delete source data, install software or browse the web. The application runs with your Windows account permissions; there is no operating-system folder sandbox.');self.render()
    def closeEvent(self,event):
        if self.busy:self.statusBar().showMessage('Please wait for the current model or file request to finish.');event.ignore();return
        if self.current:self.current['draft']=self.composer.toPlainText();self.save(self.current)
        self.closing=True;self.scroll_animation.stop();self.timer.stop();self.telegram.timer.stop();self.telegram.stop();self.model.stop();event.accept()
