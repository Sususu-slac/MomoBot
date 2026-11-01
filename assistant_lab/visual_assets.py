"""Project-owned icon and an allowlist of local chat stickers."""
from functools import lru_cache
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from .config import ROOT

ASSETS=ROOT/'assets'
APP_ICON=ASSETS/'momobot-orange-kitten.ico'
STICKERS={'kitten_hi':{'chat':ASSETS/'momobot-orange-hi-chat.png','telegram':ASSETS/'momobot-orange-hi.webp'}}

@lru_cache(maxsize=4)
def sticker_pixmap(identity):
    asset=STICKERS.get(identity)
    if not asset:return QPixmap()
    return QPixmap(str(asset['chat'])).scaled(208,208,Qt.KeepAspectRatio,Qt.SmoothTransformation)
