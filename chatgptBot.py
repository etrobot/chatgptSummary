import commonTools as tl
import os,logging,json
from EdgeGPT import Chatbot, ConversationStyle
import poe
import asyncio

class ChatBot():
    def __init__(self):
        if os.path.isfile('./cookies.json'):
            with open('./cookies.json', 'r') as f:
                cookies = json.load(f)
            self.bot = Chatbot(cookies=cookies,proxy=tl.conf.get('proxy'))
        else:
            self.bot = poe.Client(tl.conf.get('Cookie'),proxy=tl.conf.get('proxy'))

    def reply(self, queryText):
        reply_text = None
        if hasattr(self.bot,'channel'):
            for reply in self.bot.send_message(tl.conf.get('llm',default='a2'), queryText,with_chat_break=True):
                reply_text = reply['text']
        else:
            reply = asyncio.run(self.bot.ask(prompt=queryText, conversation_style=ConversationStyle.creative, wss_link="wss://sydney.bing.com/sydney/ChatHub"))
            reply_text=reply["item"]["messages"][1]["adaptiveCards"][0]["body"][0]["text"]
        return reply_text
