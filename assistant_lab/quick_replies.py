"""Immediate replies to standalone social messages; never interpret task inputs."""
from __future__ import annotations
import re

def greeting_sticker(text: str) -> str | None:
    value=text.casefold().strip().strip('.,!?。！？，、… ').strip()
    if (re.fullmatch(r'(?:hi|hello|hey)(?:\s+there|[,\s]+momobot)?',value)
        or value in ('good morning','good afternoon','good evening')
        or re.fullmatch(r'(?:你好|您好|嗨|哈喽)(?:[，,\s]*momobot)?',value)):
        return 'kitten_hi'
    return None


def quick_reply(text: str) -> str | None:
    value=text.casefold().strip().strip('.,!?。！？，、… ').strip()
    if re.fullmatch(r'(?:hi|hello|hey)(?:\s+there|[,\s]+momobot)?',value) or value in ('good morning','good afternoon','good evening'):
        return "Hi! I'm MomoBot. What would you like to work on?"
    if re.fullmatch(r'(?:你好|您好|嗨|哈喽)(?:[，,\s]*momobot)?',value):
        return '你好，我是 MomoBot。今天想做什么？'
    if value in ('thanks','thank you','thanks momobot','thank you momobot'):
        return "You're welcome!"
    if value in ('谢谢','谢谢你','多谢','谢谢momobot','谢谢 momobot'):
        return '不客气！'
    if value in ('who are you','what is your name',"what's your name"):
        return "I'm MomoBot, your local assistant for reconstruction, segmentation and fine-tuning."
    if value in ('你是谁','你叫什么','你叫什么名字','你的名字是什么'):
        return '我是 MomoBot，你的本地重建、分割和微调助手。'
    if value in ('what can you do','what can you help me with'):
        return 'I can reconstruct data, generate trial reconstructions, find rotation centers, segment images and fine-tune models. Tell me your task and paste the data path.'
    if value in ('你能做什么','你可以做什么'):
        return '我可以重建数据、生成试重建图片、查找旋转中心、分割图片和微调模型。告诉我想做什么，再发来数据路径即可。'
    return None
