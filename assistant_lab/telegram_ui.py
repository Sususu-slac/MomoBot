"""Telegram settings and the adapter to the existing desktop task controller."""
from __future__ import annotations
import time,re
from pathlib import Path
from PySide6.QtCore import QObject,QTimer,Qt,QUrl
from PySide6.QtGui import QDesktopServices
from .telegram_setup import TelegramSetupDialog
from .telegram_bridge import TelegramSettings,TelegramBridge
from .quick_replies import quick_reply,greeting_sticker
from .visual_assets import STICKERS
from .chat_flow import find_entry

HELP=('MomoBot is connected to the computer. Chat naturally and paste paths to data on that computer.\n'
      '/tasks — list saved tasks\n/use TASK_ID — switch task\n/new — new task\n/status — current task progress\n'
      '/stop — safely stop this task\n/curve — send the saved search curve\n/image — send the saved best image\n'
      'The computer and MomoBot must remain running and online. Text only; uploads and voice are not supported yet.')


class TelegramController(QObject):
    def __init__(self,window,autoload=True):
        super().__init__(window);self.window=window;self.settings=TelegramSettings(window.repo.root.parent/'telegram.json')
        self.bridge=None;self.dialog=None;self.username='';self.status_text='Not connected';self.connection_ready=False;self.connecting=False;self.seen={};self.stickers_seen=set();self.sent_at={};self.errors=[]
        self.timer=QTimer(self);self.timer.setInterval(800);self.timer.timeout.connect(self.sync);self.timer.start()
        self.timer.timeout.connect(self.refresh_dialog)
        if autoload and self.settings.read().get('enabled'):QTimer.singleShot(700,self.connect_saved)
    def subscribe(self,task,baseline=True):
        cfg=self.settings.read();ids=cfg.get('subscriptions',[])
        if task['id'] not in ids:ids.append(task['id'])
        self.settings.update(task_id=task['id'],subscriptions=ids)
        if baseline:
            for entry in task['messages']:
                if entry['role']=='assistant':
                    key=(task['id'],entry['id']);self.seen[key]=self.visible_text(entry);self.stickers_seen.add(key)
    def task(self):
        cfg=self.settings.read();task=self.window.tasks.get(cfg.get('task_id')) or self.window.current
        if task and task['id']!=cfg.get('task_id'):self.subscribe(task)
        return task
    def stop(self):
        if self.bridge:self.bridge.stop();self.bridge=None
        self.connection_ready=False;self.connecting=False
    def connect_saved(self):
        self.stop()
        try:
            bridge=TelegramBridge(self.settings,parent=self);self.bridge=bridge
            bridge.status.connect(lambda value,b=bridge:self.set_status(value) if self.bridge is b else None)
            bridge.ready.connect(lambda value,b=bridge:self.connected(value) if self.bridge is b else None)
            bridge.paired.connect(lambda value,b=bridge:self.paired(value) if self.bridge is b else None)
            bridge.incoming.connect(lambda value,b=bridge:self.receive(value) if self.bridge is b else None)
            for identity in self.settings.read().get('subscriptions',[]):
                if identity in self.window.tasks:
                    for entry in self.window.tasks[identity]['messages']:
                        if entry['role']=='assistant':
                            key=(identity,entry['id']);self.seen[key]=self.visible_text(entry);self.stickers_seen.add(key)
            self.set_status('Connecting…');bridge.start()
        except Exception:
            self.set_status('Could not unlock Telegram credentials. Enter the token again on this Windows account.')
    def connected(self,me):
        self.username=me.get('username','');self.connection_ready=True;self.connecting=False
        if not self.settings.read().get('owner_id'):self.ensure_pairing_code()
        self.set_status('Connected as @'+self.username)
    def set_status(self,value):
        if value=='Connecting…':self.connecting=True
        elif not self.connection_ready:self.connecting=False
        self.status_text=value;self.refresh_dialog()
    def paired(self,value):
        self.task();self.set_status('Connected · phone paired');self.refresh_dialog()
        dialog=self.dialog
        if dialog:QTimer.singleShot(1800,lambda:self.close_after_pairing(dialog))
    def close_after_pairing(self,dialog):
        if self.dialog is dialog and self.connection_ready and self.settings.read().get('owner_id'):dialog.close()
    def ensure_pairing_code(self):
        if not self.bridge or not self.connection_ready or not self.username or self.settings.read().get('owner_id'):return
        if not self.bridge.pair_code or time.monotonic()>=self.bridge.pair_expires:self.bridge.new_pair_code()
    def pairing_link(self):
        if self.bridge and self.connection_ready and re.fullmatch(r'[A-Za-z0-9_]{5,32}',self.username) and self.bridge.pair_code and time.monotonic()<self.bridge.pair_expires and not self.settings.read().get('owner_id'):
            return 'https://t.me/'+self.username+'?start='+self.bridge.pair_code
        return ''
    def pair_phone(self):
        if not self.bridge or not self.username:self.set_status('Connect the bot first.');return
        if self.settings.read().get('owner_id'):self.set_status('A phone is already paired. Disconnect and unpair it first.');return
        self.bridge.new_pair_code();self.refresh_dialog()
    def receive(self,event):
        if not self.bridge or event.get('owner_id')!=self.settings.read().get('owner_id'):return
        text=event['text'];parts=text.split(maxsplit=1);command=parts[0].split('@')[0].casefold() if text.startswith('/') else ''
        argument=parts[1].strip() if len(parts)>1 else '';w=self.window
        if command in ('/start','/help'):self.reply(HELP);return
        if command=='/tasks':
            self.reply('\n\n'.join(f"{t['title']} · {t['state']}\n/use {t['id']}" for t in list(w.tasks.values())[:25]) or 'No tasks yet. Use /new.');return
        if command=='/use':
            task=w.tasks.get(argument)
            if not task:self.reply('Task not found. Use /tasks, then copy its /use command.');return
            self.subscribe(task);self.reply('Selected: '+task['title']);return
        if command=='/new':
            task=w.repo.create();task['settings']['gpu']=w.default_gpu;w.tasks={task['id']:task,**w.tasks};w.save(task);w.refresh_list();self.subscribe(task,False);self.sync();return
        task=self.task()
        if not task:self.reply('No task selected. Use /new.');return
        low=text.casefold().strip(' .!。！')
        if command=='/stop' or low in ('stop','safe stop','停止','停止任务'):
            w.stop_task(task);self.sync();return
        if command=='/status' or low in ('status','progress','进度','现在怎么样了'):
            w.show_status(task);self.sync();return
        if command in ('/curve','/image'):text='Show the saved curve' if command=='/curve' else 'Show the best image'
        elif command:self.reply('Unknown command. Use /help or type your request normally.');return
        if w.busy:
            instant=quick_reply(text)
            if instant:
                w.add(task,'user',text);w.add(task,'assistant',instant,sticker=greeting_sticker(text));w.render_if_current(task);self.sync()
            else:self.reply('MomoBot is handling another message or loading the model. This request has not run; please send it again shortly.')
            return
        w.submit_text(task,text,remote=True);self.sync()
    def reply(self,text):
        if self.bridge:self.bridge.send_text(text)
    @staticmethod
    def visible_text(entry):
        if entry.get('progress',{}).get('state')=='working':
            events=entry.get('activity',[]);phase=events[-1]['text'] if events else ''
            return 'Working…'+('\n'+phase if phase else '')
        return entry.get('text','')
    def sync(self):
        if not self.bridge or not self.settings.read().get('owner_id'):return
        cfg=self.settings.read();now=time.monotonic()
        for identity in cfg.get('subscriptions',[]):
            task=self.window.tasks.get(identity)
            if not task:continue
            for entry in task['messages']:
                if entry['role']!='assistant':continue
                key=(identity,entry['id']);text=self.visible_text(entry)
                if not text:continue
                working=entry.get('progress',{}).get('state')=='working'
                if working and now-self.sent_at.get(key,-100)<6:continue
                if self.seen.get(key)!=text and self.bridge.send_text(text,key=':'.join(key)):
                    self.seen[key]=text;self.sent_at[key]=now
                sticker=STICKERS.get(entry.get('sticker'))
                if sticker and not working and key not in self.stickers_seen:
                    if self.bridge.send_sticker(sticker['telegram'],key='sticker:'+':'.join(key)):self.stickers_seen.add(key)
    def show(self):
        if self.dialog:
            self.refresh_dialog();self.dialog.show();self.dialog.raise_();self.dialog.activateWindow();return
        dialog=TelegramSetupDialog(self);self.dialog=dialog;self.token_input=dialog.token_input
        dialog.destroyed.connect(self.dialog_closed);self.refresh_dialog();dialog.show();dialog.raise_();dialog.activateWindow()
        if dialog.page_name=='token':self.token_input.setFocus()
    def dialog_closed(self):self.dialog=None
    def refresh_dialog(self):
        if self.dialog:self.dialog.refresh()
    def configure(self):
        token=self.token_input.text().strip()
        try:
            self.stop()
            if token:self.settings.configure(token)
            elif self.settings.token():self.settings.update(enabled=True)
            else:raise ValueError('Paste the token from BotFather first.')
            self.token_input.clear();self.username='';self.connect_saved()
        except ValueError as error:self.set_status(str(error))
        except Exception:self.set_status('Could not save the token with Windows encryption.')
    def disconnect(self):self.stop();self.settings.update(enabled=False);self.set_status('Disconnected')
    def unpair(self):
        self.disconnect();self.settings.update(owner_id=None,chat_id=None,subscriptions=[],task_id=None);self.seen.clear();self.stickers_seen.clear();self.sent_at.clear();self.refresh_dialog()
    def open_pair_link(self):
        link=self.pairing_link()
        if link:QDesktopServices.openUrl(QUrl(link))
