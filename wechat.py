# encoding:utf-8

"""
wechat channel
"""

import itchat
from itchat.content import *
from poe import poeBot
import pandas as pd
import commonTools as tl


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
        self.chatBot=poeBot(tl.conf)
        pass

    def startup(self):
        # login by scan QRCode
        itchat.auto_login(hotReload=True)
        # start message listener
        itchat.run()

    def msg49(self,msg:dict):
        if msg['FileName'] not in tl.posts.df.index:
            df = pd.DataFrame(data=[[tl.dealWxUrl(msg['Url']), '']], index=[msg['FileName']],
                              columns=['Url', 'Summary'])
            tl.posts.df = tl.posts.df.append(df)
            tl.posts.df.to_csv(tl.posts.filename, index_label='FileName')

    def handle(self, msg):
        tl.log.info(msg)
        from_user_id = msg['FromUserName']
        to_user_id = msg['ToUserName']              # 接收人id
        other_user_id = msg['User']['UserName']     # 对手方id
        content = msg['Text']
        if content == "McDonald's ":
            self.chatBot.clear_context(self.chatBot.chat_id)
        quote='\n- - - - - - - - - - - - - - -\n'
        if from_user_id == other_user_id:
            match_prefix = tl.check_prefix(content, tl.conf.get('single_chat_prefix'))
            query=''
            prompt=''
            filename = ''
            if msg['MsgType'] == 49:
                self.msg49(msg)
                filename = msg['FileName']
                prompt = '总结要点，带序号:'
                query = tl.ripPost(filename, tl.posts.df)
            elif '[Link]' in content or '[链接]' in content:
                filename = tl.extractWxTitle(content)
                prompt = content.split(quote)[-1][len(match_prefix):]
                query=tl.ripPost(filename,tl.posts.df)
            elif quote in content :
                querys=content.split(quote)
                query=querys[0]
                prompt=querys[1]
            elif match_prefix != '':
                prompt = content[len(match_prefix):]
            tl.thread_pool.submit(self._do_send, query,from_user_id,prompt,filename)




    def handle_group(self, msg):
        group_name = msg['User'].get('NickName', None)
        if not group_name:
            return ""
        if not (group_name in tl.conf.get('group_name_white_list') or 'ALL_GROUP' in tl.conf.get(
                'group_name_white_list')):
            return ""
        tl.log.debug(group_name)
        tl.log.debug(msg)
        if msg['MsgType']==49:
            self.msg49(msg)
            return
        if '[Message cannot be displayed]' in msg['Content']:
            query=tl.dealText(tl.ripBili(tl.posts.df[tl.posts.df['Url'].str.contains('23.tv')]['Url'].iloc[-1]))
            tl.thread_pool.submit(self._do_send_group, query, msg, msg['FileName'], '总结要点，带序号：')
            return

        quote = '\n- - - - - - - - - - - - - - -\n'
        if not msg['IsAt'] or not quote in msg['Content']:
            return
        content = msg['Content'].split(quote)
        name=msg['User']['Self']['DisplayName']
        if name == '':
            name=msg['User']['Self']['NickName']
        prompt = content[-1][len(name)+1:]
        query = content[0][len(msg['ActualNickName'])+1:]
        title=''
        if '[Link]' in msg['Content'] or '[链接]' in msg['Content']:
            title = tl.extractWxTitle(msg['Content'])
            query= tl.ripPost(title,tl.posts.df)
        if query is not None:
            tl.thread_pool.submit(self._do_send_group,query,msg,title,prompt)

    def send(self, msg, receiver):
        # tl.log.info('[WX] sendMsg={}, receiver={}'.format(msg, receiver))
        itchat.send(msg, toUserName=receiver)

    def _do_send(self, query,reply_user_id,prompt,title):
        try:
            if query=='' and prompt=='':
                return
            context = dict()
            context['from_user_id'] = reply_user_id
            queryText = tl.conf.get("character_desc", "") + prompt
            if query!='':
                queryText=queryText+'\n『%s\n』'%query
            if len(query)>2000 or '总结' in prompt:
                queryText = queryText +'\nTL;DR;Use Chinese.'
            reply_text = self.chatBot.reply(queryText,context)
            if reply_text:
                self.send(tl.conf.get("single_chat_reply_prefix") + reply_text, reply_user_id)
                if title != '' and title in tl.posts.df.index and self.chatBot.state == 'complete':
                    tl.posts.update(key=title,field= 'Summary',content=reply_text)
                
        except Exception as e:
            tl.log.exception(e)

    def _do_send_group(self,query,msg,title,prompt):
        if not query:
            return
        if title !='' and title in tl.posts.df.index and tl.posts.df.loc[title]['Summary'] != '' and ('总结' in prompt or prompt==''):
            query = tl.posts.df.loc[title]['Summary'].split('[ChatGPT]')[-1]
            self.send(query, msg['User']['UserName'])
            return
        context = dict()
        context['from_user_id'] = msg['ActualUserName']
        group_id = msg['User']['UserName']
        query = tl.conf.get('character_desc', '') + prompt + '\n『%s』'%query
        if len(prompt) < 4 or len(query) > 600:
            query = query + '\nTL;DR; Use Chinese.'
        reply_text = self.chatBot.reply(query, context)
        if reply_text:
            self.send('@' + msg['ActualNickName'] + ' ' + reply_text.strip(), group_id)
            if title != '' and title in tl.posts.df.index and self.chatBot.state=='complete':
                tl.posts.update(key=title,field= 'Summary',content=reply_text)

