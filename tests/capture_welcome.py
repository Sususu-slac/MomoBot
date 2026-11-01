import os,sys
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from PySide6.QtCore import QTimer
from assistant_lab.chat_window import ChatWindow
from assistant_lab.config import ROOT
app=QApplication([])
for f in ['segoeui.ttf','segoeuib.ttf','seguisym.ttf']:QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
app.setFont(QFont('Segoe UI',10));app.setStyle('Fusion');w=ChatWindow(autoload=False);w.show()
def capture():
 w.grab().save(str(ROOT/'test_outputs/simple_welcome.png'));w.close();app.quit()
QTimer.singleShot(300,capture);app.exec()
