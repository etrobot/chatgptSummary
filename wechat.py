# encoding:utf-8

"""
wechat channel
"""
import itchat
import json,re
from itchat.content import *
from concurrent.futures import ThreadPoolExecutor
import requests
from http.cookies import SimpleCookie
from chatgptBot import *

import pandas as pd
from bs4 import BeautifulSoup

thread_pool = ThreadPoolExecutor(max_workers=8)
log = logging.getLogger('log')
log.setLevel(logging.DEBUG)

@itchat.msg_register([TEXT,SHARING])
def handler_single_msg(msg):
    weChat().handle(msg)
    return None


@itchat.msg_register([TEXT,SHARING], isGroupChat=True)
def handler_group_msg(msg):
    weChat().handle_group(msg)
    return None


class weChat():
    def __init__(self):
        
        with open('config.json') as fr:
            self.conf = json.loads(fr.read())
        self.chatBot=ChatGPTBot(self.conf)
        self.csvfile='./articles.csv'
        self.articles=pd.read_csv(self.csvfile,index_col='FileName',keep_default_na=False)
        pass

    def startup(self):
        # login by scan QRCode
        itchat.auto_login(hotReload=True)
        # start message listener
        itchat.run()


    def handle(self, msg):
        log.debug(msg)
        from_user_id = msg['FromUserName']
        to_user_id = msg['ToUserName']              # 接收人id
        other_user_id = msg['User']['UserName']     # 对手方id
        content = msg['Text']
        if content == "McDonald's ":
            self.chatBot.chatbot.reset_chat()
        if msg['MsgType']==49 and msg['FileName'] not in self.articles.index:
            df=pd.DataFrame(data=[[msg['Url'],'']],index=[msg['FileName']],columns=['Url','Summary'])
            self.articles=self.articles.append(df)
            self.articles.to_csv(self.csvfile,index_label='FileName')
        match_prefix = self.check_prefix(content, self.conf.get('single_chat_prefix'))
        if from_user_id == other_user_id and match_prefix is not None:
            prompt = content[len(match_prefix):]
            filename = ''
            if '[Link]' in content or '[链接]' in content:
                filename = self.extractWxTitle(content)
                prompt = content.split('\n- - - - - - - - - - - - - - -\n')[-1][len(match_prefix):]
                query=self.ripPost(filename)
            else:
                query=content[len(match_prefix):]
            if query is not None:
                thread_pool.submit(self._do_send, query,from_user_id,prompt,filename)

        elif to_user_id == other_user_id and match_prefix:
            # 自己给好友发送消息
            str_list = content.split(match_prefix, 1)
            if len(str_list) == 2:
                content = str_list[1].strip()
                self.articles.at[self.extractWxTitle(content), 'Summary'] = content
                self.articles.to_csv(self.csvfile,index_label='FileName')


    def handle_group(self, msg):
        group_name = msg['User'].get('NickName', None)
        if not group_name:
            return ""
        if not (group_name in self.conf.get('group_name_white_list') or 'ALL_GROUP' in self.conf.get(
                'group_name_white_list')):
            return ""
        log.debug(group_name)
        log.debug(msg)
        if msg['MsgType']==49 and msg['FileName'] not in self.articles.index and 'mp.weixin.qq.com' in msg['Url']:
            df=pd.DataFrame(data=[[self.dealWxUrl(msg['Url']),'']],index=[msg['FileName']],columns=['Url','Summary'])
            self.articles=self.articles.append(df)
            self.articles.to_csv(self.csvfile,index_label='FileName')
        if not msg['IsAt']:
            return
        content = msg['Content']
        if not('[Link]' in content or '[链接]' in content) :
            return
        prompt = content.split('\n- - - - - - - - - - - - - - -\n')[-1][len(msg['User']['Self']['NickName'])+1:]
        log.debug(msg['User']['Self']['NickName'])
        log.debug(prompt)
        filename = self.extractWxTitle(content)
        query=self.ripPost(filename)
        if query is not None:
            thread_pool.submit(self._do_send_group,query,msg,filename,prompt)

    def send(self, msg, receiver):
        logging.info('[WX] sendMsg={}, receiver={}'.format(msg, receiver))
        itchat.send(msg, toUserName=receiver)

    def _do_send(self, query,reply_user_id,prompt,title):
        try:
            if not query:
                return
            context = dict()
            context['from_user_id'] = reply_user_id
            self.waiting = True
            if title!='':
                query = self.conf.get("character_desc", "") + prompt + '\n『%s\n』'%query+'\nTL;DR;'
            reply_text = self.chatBot.reply(query,context)
            if reply_text:
                if title!='':
                    self.articles.at[title,'Summary']=reply_text
                    self.articles.to_csv(self.csvfile,index_label='FileName')
                self.send(self.conf.get("single_chat_reply_prefix") + reply_text, reply_user_id)
                
        except Exception as e:
            logging.exception(e)
            self.waiting = False

    def _do_send_group(self,query,msg,title,prompt):
        if not query:
            return
        context = dict()
        context['from_user_id'] = msg['ActualUserName']
        query = self.conf.get("character_desc", "") + prompt + '\n『%s\n』'%query+'\nTL;DR;'
        reply_text = self.chatBot.reply(query, context)
        reply_text = '@' + msg['ActualNickName'] + ' ' + reply_text.strip()
        if reply_text:
            self.articles.at[title, 'Summary'] = reply_text
            self.articles.to_csv(self.csvfile, index_label='FileName')
            self.send(reply_text, msg['User']['UserName'])
        

    def check_prefix(self, content, prefix_list):
        for prefix in prefix_list:
            if prefix in content:
                return prefix
        return None

    def dealWxUrl(self,rawurl:str):
        cookie = SimpleCookie()
        cookie.load(rawurl.split('://')[1][len('mp.weixin.qq.com/s?__'):].replace('&amp', ''))
        cookies = {k: v.value for k, v in cookie.items()}
        realurl = "https://mp.weixin.qq.com/s?__biz={biz}&mid={mid}&idx={idx}&sn={sn}".format(
            biz=cookies["biz"],
            mid=cookies["mid"],
            idx=cookies["idx"],
            sn=cookies["sn"],
        )
        return realurl

    def extractWxTitle(self,txt):
        pattern = r'\[Link\]\s+(.*?)"\n- - - - - - - - - - - - - - -\n'
        if '[链接]' in txt:
            pattern = r'\[链接\]+(.*?)」\n- - - - - - - - - - - - - - -\n'
        match = re.search(pattern, txt)
        if match:
            log.debug(match.group(1))
            return match.group(1)

    def ripPost(self,filename):
        row=self.articles.loc[filename]
        if row['Summary']!='':
            return row['Summary']
        res = requests.get(row['Url'])
        soup = BeautifulSoup(res.text, "html.parser")
        query=soup.find(id='js_content').get_text(separator="\n")
        if len(query)==0:
            discription = re.sub(r'\\x[0-9a-fA-F]{2}', '', soup.find('meta', {'name': 'description'}).attrs['content'])
            query = discription + query
        else:
            query1 = query[:self.conf.get('headLen', 1500)].split('\n')[:-1]
            query1.extend(query[-self.conf.get('tailLen', 1000):].split('\n')[1:])
            query = list(set(query1))
            query.sort(key=query1.index)
            query = '\n'.join(query)
        return query
