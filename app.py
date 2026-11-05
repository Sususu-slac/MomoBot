from __future__ import annotations
import sys,traceback,hashlib,os
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtGui import QFont,QFontDatabase,QIcon
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from PySide6.QtCore import QTimer,Qt
from assistant_lab.chat_window import ChatWindow
from assistant_lab.config import STATE_ROOT,VERSION
from assistant_lab.visual_assets import APP_ICON

def main():
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs,True)
    app=QApplication(sys.argv);app.setApplicationName('MomoBot');app.setApplicationVersion(VERSION);app.setWindowIcon(QIcon(str(APP_ICON)))
    def hook(kind,value,tb):
        log=STATE_ROOT/'outputs/gui_errors.log';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('a',encoding='utf-8') as f:traceback.print_exception(kind,value,tb,file=f)
        QMessageBox.critical(None,'MomoBot',str(value))
    sys.excepthook=hook
    name=('BL62_Assistant_Chat_'+hashlib.sha256(os.environ['MOMOBOT_STATE_ROOT'].encode()).hexdigest()[:16]) if os.environ.get('MOMOBOT_STATE_ROOT') else 'BL62_Assistant_Chat_Simple';socket=QLocalSocket();socket.connectToServer(name)
    if socket.waitForConnected(150):socket.write(b'telegram' if '--telegram-setup' in sys.argv else b'show');socket.flush();socket.waitForBytesWritten(200);return 0
    server=QLocalServer();QLocalServer.removeServer(name)
    if not server.listen(name):return 1
    for font in ['segoeui.ttf','segoeuib.ttf','seguisym.ttf','msyh.ttc']:QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
    selftest='--self-test' in sys.argv
    app.setFont(QFont('Segoe UI',10));app.setStyle('Fusion');window=ChatWindow(autoload=not selftest);window.show()
    if selftest:
        import json
        from assistant_lab.config import MODEL_PROFILES,DEFAULT_PROFILE
        target=Path(sys.argv[sys.argv.index('--self-test')+1]);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(dict(version=VERSION,profiles=list(MODEL_PROFILES),default_profile=DEFAULT_PROFILE,
            sop_available=hasattr(window,'sop'),delete_button_present=window.delete_btn.text()=='Delete task',model_started=window.model.running),indent=2),encoding='utf-8')
        window.close();app.processEvents();return 0
    if '--telegram-setup' in sys.argv:QTimer.singleShot(900,window.telegram.show)
    def activate():
        client=server.nextPendingConnection()
        request=b''
        if client:
            if not client.bytesAvailable():client.waitForReadyRead(200)
            request=bytes(client.readAll());client.close();client.deleteLater()
        window.showNormal();window.raise_();window.activateWindow()
        if request==b'telegram':window.telegram.show()
    server.newConnection.connect(activate)
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
