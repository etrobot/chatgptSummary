# encoding:utf-8

"""
wechat channel
"""
import itchat
import json,re
from itchat.content import *
from concurrent.futures import ThreadPoolExecutor
import requests
import io
from http.cookies import SimpleCookie
import logging
from chatgptBot import *

import pandas as pd
from bs4 import BeautifulSoup

thead_pool = ThreadPoolExecutor(max_workers=8)
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
        self.waiting=False
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
        if self.waiting:
            log.info('waiting')
            return
        log.debug(msg)
        from_user_id = msg['FromUserName']
        to_user_id = msg['ToUserName']              # 接收人id
        other_user_id = msg['User']['UserName']     # 对手方id
        content = msg['Text']
        if msg['MsgType']==49 and msg['FileName'] not in self.articles.index:
            df=pd.DataFrame(data=[[msg['Url'],'']],index=[msg['FileName']],columns=['Url','Summary'])
            self.articles=self.articles.append(df)
            self.articles.to_csv(self.csvfile,index_label='FileName')
        match_prefix = self.check_prefix(content, self.conf.get('single_chat_prefix'))
        if from_user_id == other_user_id and match_prefix is not None:
            filename=self.extractWxTitle(content)
            if '[Link]' in content or '[链接]' in content:
                prompt=self.ripPost(filename)
            else:
                prompt=content[len(match_prefix):]
            if prompt is not None:
                thead_pool.submit(self._do_send, prompt, from_user_id)

        elif to_user_id == other_user_id and match_prefix:
            # 自己给好友发送消息
            str_list = content.split(match_prefix, 1)
            if len(str_list) == 2:
                content = str_list[1].strip()
                self.articles.at[self.extractWxTitle(content), 'Summary'] = content
                self.articles.to_csv(self.csvfile,index_label='FileName')


    def handle_group(self, msg):
        if self.waiting:
            log.info('waiting')
            return
        log.debug(msg)
        group_name = msg['User'].get('NickName', None)
        if not group_name:
            return ""
        if (group_name in self.conf.get('group_name_white_list') or 'ALL_GROUP' in self.conf.get(
                'group_name_white_list')):
            return ""
        if msg['MsgType']==49 and msg['FileName'] not in self.articles.index:
            df=pd.DataFrame(data=[[self.dealWxUrl(msg['Url']),'']],index=[msg['FileName']],columns=['Url','Summary'])
            self.articles=self.articles.append(df)
            self.articles.to_csv(self.csvfile,index_label='FileName')
        origin_content = msg['Content']
        content = msg['Content']
        content_list = content.split(' ', 1)
        context_special_list = content.split('\u2005', 1)
        if len(context_special_list) == 2:
            content = context_special_list[1]
        elif len(content_list) == 2:
            content = content_list[1]

        match_prefix = msg['IsAt'] or self.check_prefix(origin_content, self.conf.get('group_chat_prefix'))
        if match_prefix is not None:
            filename=self.extractWxTitle(content)
            log.info(filename)
            prompt=None
            if '[Link]' in content or '[链接]' in content:
                prompt=self.ripPost(filename)
            if prompt is not None:
                thead_pool.submit(self._do_send_group,prompt, msg)

    def send(self, msg, receiver):
        logging.info('[WX] sendMsg={}, receiver={}'.format(msg, receiver))
        itchat.send(msg, toUserName=receiver)

    def _do_send(self, query, reply_user_id):
        try:
            if not query:
                return
            if '--$$$#--' in query:
                titleAndTxt = query.split('--$$$#--')
                title, query = titleAndTxt[0], titleAndTxt[1]
            if len(query)>3000:
                self.send(self.conf.get("single_chat_reply_prefix") + '文章超过三千字，chatGPT不接', reply_user_id)
                return
            context = dict()
            context['from_user_id'] = reply_user_id
            self.waiting = True
            prompt=query
            if '--$$$#--' in query:
                prompt = self.conf.get("character_desc", "") + ' ' + query
            reply_text = self.chatBot.reply(prompt,context)
            if reply_text:
                if '--$$$#--' in query:
                    self.articles.at[title,'Summary']=reply_text
                    self.articles.to_csv(self.csvfile,index_label='FileName')
                self.send(self.conf.get("single_chat_reply_prefix") + reply_text, reply_user_id)
                self.waiting=False
        except Exception as e:
            logging.exception(e)
            self.waiting = False

    def _do_send_group(self, query, msg):
        if not query:
            return
        if '--$$$#--' in query:
            titleAndTxt = query.split('--$$$#--')
            title, query = titleAndTxt[0], titleAndTxt[1]
        if len(query) > 3000:
            self.send('文章超过三千字，chatGPT不接', msg['User']['UserName'])
            return
        context = dict()
        context['from_user_id'] = msg['ActualUserName']
        self.waiting=True
        prompt = self.conf.get("character_desc", "") + ' ' + query
        reply_text = self.chatBot.reply(prompt, context)
        reply_text = '@' + msg['ActualNickName'] + ' ' + reply_text.strip()
        if reply_text:
            self.articles.at[title, 'Summary'] = reply_text
            self.articles.to_csv(self.csvfile, index_label='FileName')
            self.send(reply_text, msg['User']['UserName'])
        self.waiting=False

    def check_prefix(self, content, prefix_list):
        for prefix in prefix_list:
            if prefix in content:
                return prefix
            if content.startswith(prefix):
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
        log.debug(txt)
        pattern = r'\[Link\]\s+(.*?)"\n- - - - - - - - - - - - - - -\n'
        if '[链接]' in txt:
            pattern = r'\[链接\]+(.*?)」\n- - - - - - - - - - - - - - -\n'
        match = re.search(pattern, txt)
        if match:
            log.debug(match.group)
            return match.group(1)

    def ripPost(self,filename):
        row=self.articles.loc[filename]
        log.debug(row)
        if row['Summary']!='':
            return row['Summary']
        res = requests.get(row['Url'])
        soup = BeautifulSoup(res.text, "html.parser")
        discription = re.sub(r'\\x[0-9a-fA-F]{2}', '', soup.find('meta', {'name': 'description'}).attrs['content'])
        prompt=soup.find(id='js_content').text
        if len(prompt)==0:
            prompt = discription + prompt
        log.info(len(prompt))
        log.info(prompt)
        return filename+'--$$$#--'+prompt
