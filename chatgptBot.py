import time
from revChatGPT.V1 import Chatbot
import logging

# ChatGPT web接口 (暂时不可用)
class ChatGPTBot():
    def __init__(self,conf:dict):
        config = {
            "session_token": conf.get("__Secure-next-auth.session-token"),
            # "driver_exec_path": "/usr/local/bin/chromedriver"
        }
        if conf.get("proxy"):
            config['proxy']=conf.get("proxy")
        self.chatbot = Chatbot(config)

    def reply(self, query, context=None):
        try:
            user_cache = dict()
            for res in self.chatbot.ask(query):
                user_cache=res
            print(user_cache)
            return user_cache['message']
        except Exception as e:
            logging.exception(e)
            return None