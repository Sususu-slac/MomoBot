"""Private Telegram transport. Only a paired private-chat owner can submit text."""
from __future__ import annotations
import base64,ctypes,json,os,queue,re,secrets,threading,time,urllib.request,urllib.error
from pathlib import Path
from PySide6.QtCore import QObject,Signal
from .jobs import atomic_json,read_json


def protect_token(value: str, decrypt=False) -> str:
    if os.name!='nt':raise RuntimeError('Telegram credentials must be configured on Windows.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=base64.b64decode(value) if decrypt else value.encode('utf-8')
    buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    operation=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    operation.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if not operation(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):
        raise RuntimeError('Windows could not unlock/save Telegram credentials for this account.')
    try:
        result=ctypes.string_at(target.data,target.size)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:kernel.LocalFree(target.data)


class TelegramSettings:
    def __init__(self,path):self.path=Path(path);self.lock=threading.RLock()
    def read(self):
        with self.lock:return read_json(self.path)
    def update(self,**values):
        with self.lock:
            data=read_json(self.path);data.update(values);atomic_json(self.path,data);return data
    def token(self):
        value=self.read().get('token_encrypted','')
        return protect_token(value,True) if value else ''
    def configure(self,token):
        if not re.fullmatch(r'[0-9]{5,}:[A-Za-z0-9_-]{20,}',token):raise ValueError('Paste the complete token from BotFather.')
        encrypted=protect_token(token)
        with self.lock:
            old=self.read();changed=token!=self.token()
            if changed:old={}
            old.update(token_encrypted=encrypted,enabled=True)
            atomic_json(self.path,old)


class TelegramError(RuntimeError):
    def __init__(self,text,code=0,retry_after=0):super().__init__(text);self.code=code;self.retry_after=retry_after


class TelegramAPI:
    def __init__(self,token):self.token=token
    def call(self,method,payload=None,file=None,timeout=12):
        if file:
            path=Path(file);boundary='MomoBot'+secrets.token_hex(12);parts=[]
            for key,value in (payload or {}).items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            field={'sendPhoto':'photo','sendSticker':'sticker'}.get(method,'document');name=path.name.replace('"','_').replace('\r','_').replace('\n','_')
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
            parts.extend([path.read_bytes(),f'\r\n--{boundary}--\r\n'.encode()]);body=b''.join(parts);content='multipart/form-data; boundary='+boundary
        else:body=json.dumps(payload or {}).encode();content='application/json'
        req=urllib.request.Request('https://api.telegram.org/bot'+self.token+'/'+method,data=body,headers={'Content-Type':content})
        try:
            with urllib.request.urlopen(req,timeout=timeout) as response:data=json.load(response)
        except urllib.error.HTTPError as error:
            try:data=json.loads(error.read())
            except (ValueError,OSError):data={}
            detail=str(data.get('description','Request rejected')).replace(self.token,'[redacted]')
            raise TelegramError(f'Telegram {error.code}: {detail[:200]}',error.code,data.get('parameters',{}).get('retry_after',0)) from None
        except (OSError,ValueError):raise TelegramError('Cannot reach Telegram. Check the internet connection; retrying.') from None
        if not data.get('ok'):raise TelegramError('Telegram rejected the request.',data.get('error_code',0))
        return data['result']


class TelegramBridge(QObject):
    incoming=Signal(dict);status=Signal(str);ready=Signal(dict);paired=Signal(dict)
    def __init__(self,settings,api=None,parent=None):
        super().__init__(parent);self.settings=settings;self.api=api or TelegramAPI(settings.token());self.stopped=threading.Event()
        self.outbox=queue.Queue(maxsize=200);self.guard=threading.RLock();self.latest={};self.pair_code='';self.pair_expires=0.;self.started_at=int(time.time())
    def start(self):
        self.receiver=threading.Thread(target=self.receive,name='MomoBot Telegram receiver',daemon=True)
        self.sender=threading.Thread(target=self.send_loop,name='MomoBot Telegram sender',daemon=True)
        self.receiver.start();self.sender.start()
    def stop(self):
        with self.guard:self.stopped.set();self.pair_code=''
    def new_pair_code(self):
        with self.guard:self.pair_code=secrets.token_urlsafe(12);self.pair_expires=time.monotonic()+600;return self.pair_code
    def handle_update(self,update):
        identity=update.get('update_id')
        if not isinstance(identity,int):return
        with self.guard:
            if self.stopped.is_set():return
            cfg=self.settings.read()
            if identity<int(cfg.get('offset',0)):return
            # Save before dispatch: a restart must never replay a reconstruction request.
            self.settings.update(offset=identity+1)
            msg=update.get('message',{});chat=msg.get('chat',{});user=msg.get('from',{});text=msg.get('text','').strip()
            if self.stopped.is_set() or chat.get('type')!='private' or user.get('is_bot') or not user.get('id') or chat.get('id')!=user.get('id'):return
            if msg.get('date',0)<self.started_at-5:return
            owner=cfg.get('owner_id')
            if not owner:
                match=re.fullmatch(r'/(?:start|pair)\s+([A-Za-z0-9_-]+)',text)
                if not match or not self.pair_code or time.monotonic()>self.pair_expires or not secrets.compare_digest(match[1],self.pair_code):return
                owner=user['id'];self.pair_code='';self.pair_expires=0
                self.settings.update(owner_id=owner,chat_id=chat['id'])
                self.paired.emit({'owner_id':owner});self.send_text('Connected to MomoBot. Send a message or use /tasks, /new, /status or /help.');return
            if user['id']!=owner or chat['id']!=cfg.get('chat_id'):return
            if msg.get('forward_origin') or msg.get('sender_chat'):
                self.send_text('Please type your request directly; forwarded messages are not executed.');return
            if not text:
                self.send_text('Please send text and paths to data on the computer. Voice messages and file uploads are not supported yet.');return
            self.incoming.emit({'text':text,'message_id':msg.get('message_id'),'owner_id':owner})
    def receive(self):
        delay=1
        while not self.stopped.is_set():
            try:
                me=self.api.call('getMe');info=self.api.call('getWebhookInfo')
                if info.get('url'):self.status.emit('This bot already uses a webhook. Use a separate bot for MomoBot.');return
                self.ready.emit(me);break
            except TelegramError as error:
                self.status.emit(str(error))
                if error.code in (401,403):return
                if self.stopped.wait(delay):return
                delay=min(delay*2,30)
        while not self.stopped.is_set():
            try:
                updates=self.api.call('getUpdates',{'offset':self.settings.read().get('offset',0),'timeout':20,'allowed_updates':['message']},timeout=27)
                if self.stopped.is_set():return
                for update in updates:self.handle_update(update)
                delay=1
            except TelegramError as error:
                self.status.emit(str(error))
                if error.code in (401,403,409):return
                if self.stopped.wait(max(delay,min(error.retry_after,60))):return
                delay=min(delay*2,30)
    def enqueue(self,item):
        with self.guard:
            if self.stopped.is_set() or not self.settings.read().get('owner_id'):return False
            try:
                self.outbox.put_nowait(item)
                if item[2]:self.latest[item[2]]=item[1]
                return True
            except queue.Full:self.status.emit('Telegram delivery queue is full.');return False
    def send_text(self,text,key=None):return self.enqueue(('text',str(text),key))
    def send_image(self,path):return self.enqueue(('image',str(path),None))
    def send_sticker(self,path,key=None):return self.enqueue(('sticker',str(path),key))
    def send_loop(self):
        sent={};sticker_files={};sent_sticker_keys=set()
        while not self.stopped.is_set():
            try:kind,text,key=self.outbox.get(timeout=.3)
            except queue.Empty:continue
            with self.guard:
                if self.stopped.is_set():return
                if key and self.latest.get(key)!=text:continue
            cfg=self.settings.read();chat=cfg.get('chat_id')
            if not chat:continue
            try:
                if kind=='sticker':
                    if key and key in sent_sticker_keys:continue
                    path=Path(text)
                    if not path.is_file() or path.suffix.lower()!='.webp' or path.stat().st_size>512*1024:raise TelegramError('Sticker is missing or exceeds 512 KB.',400)
                    cached=sticker_files.get((text,path.stat().st_mtime_ns));payload={'chat_id':chat}
                    if cached:payload['sticker']=cached
                    result=self.api.call('sendSticker',payload,file=None if cached else path,timeout=30)
                    file_id=result.get('sticker',{}).get('file_id')
                    if file_id:sticker_files[(text,path.stat().st_mtime_ns)]=file_id
                    if key:sent_sticker_keys.add(key)
                    if self.stopped.wait(1.05):return
                elif kind=='image':
                    path=Path(text)
                    if not path.is_file() or path.stat().st_size>48*1024**2:raise TelegramError('Result image is missing or exceeds 48 MB.',400)
                    method='sendPhoto' if path.suffix.lower() in ('.png','.jpg','.jpeg') and path.stat().st_size<8*1024**2 else 'sendDocument'
                    try:self.api.call(method,{'chat_id':chat,'caption':path.name[:150]},file=path,timeout=45)
                    except TelegramError as error:
                        if method!='sendPhoto' or error.code!=400:raise
                        self.api.call('sendDocument',{'chat_id':chat},file=path,timeout=45)
                else:
                    for n,start in enumerate(range(0,len(text),1800)):
                        part=text[start:start+1800];part_key=(key,n) if key else None;previous=sent.get(part_key) if part_key else None
                        if previous and previous[1]==part:continue
                        method='editMessageText' if previous else 'sendMessage';payload={'chat_id':chat,'text':part}
                        if previous:payload['message_id']=previous[0]
                        try:result=self.api.call(method,payload)
                        except TelegramError as error:
                            if previous and error.code==400 and 'not modified' in str(error):continue
                            if previous and error.code==400:result=self.api.call('sendMessage',{'chat_id':chat,'text':part})
                            else:raise
                        if part_key:sent[part_key]=(result['message_id'],part)
                        if self.stopped.wait(1.05):return
            except TelegramError as error:
                self.status.emit(str(error))
                if error.code in (0,429,500,502,503,504):
                    if self.stopped.wait(max(3,min(error.retry_after,60))):return
                    with self.guard:
                        if not key or self.latest.get(key)==text:self.enqueue((kind,text,key))
