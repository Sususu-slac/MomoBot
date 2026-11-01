"""Two-step Telegram setup: token, then a private phone-pairing QR code."""
from __future__ import annotations
import math,time
from PySide6.QtCore import Qt,QUrl,QTimer
from PySide6.QtGui import QImage,QPainter,QColor,QPixmap,QDesktopServices
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,
 QLineEdit,QPushButton,QWidget,QMenu)


def qr_image(payload: str, minimum_size=280) -> QImage:
    import qrcode
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,border=4)
    qr.add_data(payload);qr.make(fit=True);matrix=qr.get_matrix()
    scale=max(4,math.ceil(minimum_size/len(matrix)));side=len(matrix)*scale
    result=QImage(side,side,QImage.Format_RGB32);result.fill(Qt.white)
    painter=QPainter(result)
    try:
        for y,row in enumerate(matrix):
            for x,black in enumerate(row):
                if black:painter.fillRect(x*scale,y*scale,scale,scale,QColor('black'))
    finally:painter.end()
    return result


class TelegramSetupDialog(QDialog):
    def __init__(self,controller):
        super().__init__(controller.window);self.controller=controller;self.page_name=None;self.last_qr=''
        self.setWindowTitle('Chat from Anywhere · Telegram');self.setMinimumWidth(540);self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet('QLabel#setupHeading{font-size:22px;font-weight:600} QPushButton#link{border:0;background:transparent;color:#9bd7c3;padding:5px} QLabel#phoneConnected{color:#9bd7c3;font-size:23px;font-weight:600}')
        self.layout_=QVBoxLayout(self);self.layout_.setContentsMargins(24,24,24,18);self.layout_.setSpacing(16)
        self.pages={}
        for name in ('token','pair','connected'):
            page=QWidget();box=QVBoxLayout(page);box.setContentsMargins(0,0,0,0);box.setSpacing(14);self.pages[name]=page;self.layout_.addWidget(page);page.hide()
        token_layout=self.pages['token'].layout()
        heading=QLabel('1 · Connect Telegram');heading.setObjectName('setupHeading');token_layout.addWidget(heading)
        token_label=QLabel('Bot token');token_layout.addWidget(token_label)
        row=QHBoxLayout();self.token_input=QLineEdit();self.token_input.setObjectName('telegramToken');self.token_input.setAccessibleName('Bot token')
        self.token_input.setEchoMode(QLineEdit.Password);self.token_input.setMinimumHeight(46);self.token_input.setMinimumWidth(330);self.token_input.setClearButtonEnabled(True)
        self.token_input.setStyleSheet('QLineEdit#telegramToken{background:#20303f;color:#ffffff;border:2px solid #729da9;border-radius:8px;padding:8px;font-size:15px} QLineEdit#telegramToken:focus{border-color:#72d4b3}')
        token_label.setBuddy(self.token_input);row.addWidget(self.token_input,1)
        self.paste=QPushButton('Paste token');self.paste.clicked.connect(self.token_input.paste);row.addWidget(self.paste);token_layout.addLayout(row)
        self.connect_button=QPushButton('Connect');self.connect_button.setObjectName('primary');self.connect_button.clicked.connect(controller.configure);token_layout.addWidget(self.connect_button)
        self.help_button=QPushButton('How do I get a token?');self.help_button.setObjectName('link');self.help_button.setCheckable(True);self.help_button.toggled.connect(self.toggle_help);token_layout.addWidget(self.help_button)
        self.help_panel=QWidget();help_layout=QVBoxLayout(self.help_panel);help_layout.setContentsMargins(0,0,0,0)
        help_text=QLabel('On your phone:\n1. Open Telegram and search @BotFather.\n2. Send /newbot and choose a name and username ending in bot.\n3. Copy the token and paste it into this computer.');help_text.setWordWrap(True);help_layout.addWidget(help_text)
        self.help_qr=QLabel();self.help_qr.setAlignment(Qt.AlignCenter);help_layout.addWidget(self.help_qr)
        token_layout.addWidget(self.help_panel);self.help_panel.hide()
        pair_layout=self.pages['pair'].layout();heading=QLabel('2 · Scan with your phone');heading.setObjectName('setupHeading');pair_layout.addWidget(heading)
        hint=QLabel('Scan the QR code with your phone camera.\nOpen Telegram and tap Start.');hint.setWordWrap(True);pair_layout.addWidget(hint)
        self.pair_qr=QLabel();self.pair_qr.setAlignment(Qt.AlignCenter);self.pair_qr.setAccessibleName('Phone pairing QR code');pair_layout.addWidget(self.pair_qr)
        self.bot_name=QLabel();self.bot_name.setAlignment(Qt.AlignCenter);pair_layout.addWidget(self.bot_name)
        self.waiting=QLabel('Waiting for your phone…');self.waiting.setAlignment(Qt.AlignCenter);pair_layout.addWidget(self.waiting)
        success_layout=self.pages['connected'].layout();success=QLabel('Phone connected');success.setObjectName('phoneConnected');success_layout.addWidget(success)
        self.connected_name=QLabel();success_layout.addWidget(self.connected_name)
        disconnect=QPushButton('Disconnect');disconnect.clicked.connect(controller.disconnect);success_layout.addWidget(disconnect)
        self.status=QLabel();self.status.setWordWrap(True);self.layout_.addWidget(self.status)
        footer=QHBoxLayout();self.advanced=QPushButton('Advanced');self.advanced.setObjectName('link');self.advanced.clicked.connect(self.show_advanced);footer.addWidget(self.advanced);footer.addStretch()
        close=QPushButton('Close');close.clicked.connect(self.close);footer.addWidget(close);self.layout_.addLayout(footer)
        self.apply_theme()
    def apply_theme(self):
        from bl62_theme import current_theme
        light=current_theme(self.controller.window)=='light'
        accent='#2563eb' if light else '#9bd7c3'
        self.setStyleSheet('QLabel#setupHeading{font-size:22px;font-weight:600} QPushButton#link{border:0;background:transparent;color:'+accent+';padding:5px} QLabel#phoneConnected{color:'+accent+';font-size:23px;font-weight:600}')
        self.token_input.setStyleSheet('QLineEdit#telegramToken{background:#ffffff;color:#202c3a;border:2px solid #9eb9e5;border-radius:8px;padding:8px;font-size:15px} QLineEdit#telegramToken:focus{border-color:#2563eb}' if light else 'QLineEdit#telegramToken{background:#20303f;color:#ffffff;border:2px solid #729da9;border-radius:8px;padding:8px;font-size:15px} QLineEdit#telegramToken:focus{border-color:#72d4b3}')
    def resize_to_contents(self):
        if self.isVisible():QTimer.singleShot(0,self.adjustSize)
    def toggle_help(self,checked):
        if checked and self.help_qr.pixmap().isNull():self.help_qr.setPixmap(QPixmap.fromImage(qr_image('https://t.me/BotFather',170)))
        self.help_panel.setVisible(checked);self.resize_to_contents()
    def refresh(self):
        c=self.controller;cfg=c.settings.read();owner=cfg.get('owner_id')
        stage='connected' if c.connection_ready and owner else 'pair' if c.connection_ready and c.bridge else 'token'
        if stage=='pair':
            c.ensure_pairing_code();payload=c.pairing_link()
            if payload and payload!=self.last_qr:
                self.pair_qr.setPixmap(QPixmap.fromImage(qr_image(payload)));self.last_qr=payload
            self.bot_name.setText('@'+c.username)
        else:
            self.pair_qr.clear();self.last_qr=''
        self.connected_name.setText('@'+c.username if c.username else 'Telegram is ready.')
        self.advanced.setVisible(stage!='token' or bool(owner))
        self.token_input.setPlaceholderText('Token saved · click Connect' if cfg.get('token_encrypted') else 'Paste your BotFather token here')
        self.token_input.setEnabled(not c.connecting);self.paste.setEnabled(not c.connecting);self.connect_button.setEnabled(not c.connecting)
        self.connect_button.setText('Connecting…' if c.connecting else 'Connect')
        error=c.status_text if not (c.status_text.startswith('Connected') or c.status_text in ('Not connected','Disconnected','Connecting…')) else ''
        self.status.setText(error);self.status.setVisible(bool(error))
        if stage!=self.page_name:
            self.page_name=stage
            for name,page in self.pages.items():page.setVisible(name==stage)
            self.resize_to_contents()
            if stage=='token' and not c.connecting:self.token_input.setFocus()
    def show_advanced(self):
        c=self.controller;menu=QMenu(self)
        open_link=menu.addAction('Open pairing link on this device');open_link.setEnabled(bool(c.pairing_link()));open_link.triggered.connect(c.open_pair_link)
        copy_link=menu.addAction('Copy pairing link');copy_link.setEnabled(bool(c.pairing_link()));copy_link.triggered.connect(lambda:QApplication.clipboard().setText(c.pairing_link()))
        unpair=menu.addAction('Disconnect and unpair phone');unpair.setEnabled(bool(c.settings.read().get('owner_id')));unpair.triggered.connect(c.unpair)
        menu.exec(self.advanced.mapToGlobal(self.advanced.rect().bottomLeft()))
