import commonTools as tl
import json,re
from EdgeGPT import Chatbot, ConversationStyle
import poe
import asyncio

class Bing():
    def __init__(self):
        self.bot = asyncio.run(Chatbot.create(cookie_path='./cookies.json',proxy=tl.conf.get('proxy')))

    def reply(self, querytext:str):
        reply_text=None
        reply = asyncio.run(self.bot.ask(prompt=querytext, conversation_style=ConversationStyle.precise, wss_link="wss://sydney.bing.com/sydney/ChatHub"))
        if reply:
            reply_text=reply["item"]["messages"][1]["adaptiveCards"][0]["body"][0]["text"]
            reply_text=re.sub(r'\[\^[0-9]+\^\]', '', reply_text)
        return reply_text

class Poe():
    def __init__(self):
        self.bot = poe.Client(tl.conf.get('Cookie'),proxy=tl.conf.get('proxy'))

    def reply(self, querytext:str):
        reply_text = None
        if hasattr(self.bot,'channel'):
            for reply in self.bot.send_message(tl.conf.get('llm',default='a2'), querytext,with_chat_break=True):
                reply_text = reply['text']
        return reply_text