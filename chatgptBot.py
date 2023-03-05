import json
import time

import requests
from revChatGPT.V1 import Chatbot
import logging

user_session = dict()
last_session_refresh = time.time()


class ChatGPTBot():
    def __init__(self,conf:dict):
        config = {
            "session_token":conf.get('sstoken'),
        }
        if conf.get('vika.cn'):
            vikaUrl = 'https://api.vika.cn/fusion/v1/datasheets/dstMiuU9zzihy1LzFX/records?viewId=viwoAJhnS2NMT&fieldKey=name'
            vikaCache = json.loads(requests.get(vikaUrl, headers={'Authorization': conf.get("vika.cn")}).text)['data'][
                'records']
            config["session_token"]=[x['fields']['value'] for x in vikaCache if x['recordId']=='recoeXAy2oY3E'][0]
        if conf.get('proxy'):
            config['proxy']=conf.get('proxy')
        self.chatbot = Chatbot(config)

    def reply(self, query, context=None):

        from_user_id = context['from_user_id']
        logging.getLogger('log').info("[GPT]query={}, user_id={}, session={}".format(query, from_user_id, user_session))

        if from_user_id in user_session:
            if time.time() - user_session[from_user_id]['last_reply_time'] < 60 * 5:
                self.chatbot.conversation_id = user_session[from_user_id]['conversation_id']
                self.chatbot.parent_id = user_session[from_user_id]['parent_id']
            else:
                self.chatbot.reset_chat()
        else:
            self.chatbot.reset_chat()

        logging.getLogger('log').info("[GPT]convId={}, parentId={}".format(self.chatbot.conversation_id, self.chatbot.parent_id))

        try:
            user_cache = dict()
            for res in self.chatbot.ask(query):
                user_cache=res
                logMsg=res['message'].replace('\n\n','\n')
                reply_rows=logMsg.split('\n')
                if len(reply_rows)>1 and logMsg.endswith('\n'):
                    logging.getLogger('log').debug(reply_rows[-2])
            logging.getLogger('log').info("[GPT]userId={}, res={}".format(from_user_id, res))
            user_cache['last_reply_time'] = time.time()
            user_session[from_user_id] = user_cache
            with open('./user_session.json', 'w', encoding='utf-8') as f:
                json.dump(user_session, f)
            return res['message']
        except Exception as e:
            logging.getLogger('log').exception(e)
            return None