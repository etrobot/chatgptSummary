# encoding:utf-8

"""
wechat channel
"""
import string

import itchat
import json,re
from itchat.content import *
from concurrent.futures import ThreadPoolExecutor
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
        self.posts=pd.read_csv(self.csvfile,index_col='FileName',keep_default_na=False)
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
        if msg['MsgType']==49 and msg['FileName'] not in self.posts.index:
            df=pd.DataFrame(data=[[msg['Url'],'']],index=[msg['FileName']],columns=['Url','Summary'])
            self.posts=self.posts.append(df)
            self.posts.to_csv(self.csvfile,index_label='FileName')
        match_prefix = self.check_prefix(content, self.conf.get('single_chat_prefix'))
        quote='\n- - - - - - - - - - - - - - -\n'
        if from_user_id == other_user_id and match_prefix is not None:
            prompt = content[len(match_prefix):]
            filename = ''
            if '[Link]' in content or '[链接]' in content:
                filename = self.extractWxTitle(content)
                prompt = content.split(quote)[-1][len(match_prefix):]
                query=self.ripPost(filename)
            elif quote in content:
                query=content.split(quote)
                query=query[1][len(match_prefix):]+' '+query[0]
            else:
                query=content[len(match_prefix):]
            if query is not None:
                thread_pool.submit(self._do_send, query,from_user_id,prompt,filename)

        elif to_user_id == other_user_id and match_prefix:
            # 自己给好友发送消息
            str_list = content.split(match_prefix, 1)
            if len(str_list) == 2:
                content = str_list[1].strip()
                self.posts.at[self.extractWxTitle(content), 'Summary'] = content
                self.posts.to_csv(self.csvfile,index_label='FileName')


    def handle_group(self, msg):
        group_name = msg['User'].get('NickName', None)
        if not group_name:
            return ""
        if not (group_name in self.conf.get('group_name_white_list') or 'ALL_GROUP' in self.conf.get(
                'group_name_white_list')):
            return ""
        log.debug(group_name)
        log.debug(msg)
        if msg['MsgType']==49 and msg['FileName'] not in self.posts.index:
            df=pd.DataFrame(data=[[self.dealWxUrl(msg['Url']),'']],index=[msg['FileName']],columns=['Url','Summary'])
            self.posts=self.posts.append(df)
            self.posts.to_csv(self.csvfile,index_label='FileName')
            return
        if '[Message cannot be displayed]' in msg['Content']:
            query=self.dealText(self.ripBili(self.posts[self.posts['Url'].str.contains('23.tv')]['Url'].iloc[-1]))
            thread_pool.submit(self._do_send_group, query, msg, msg['FileName'], '请用中文总结以下视频要点，带序号：')
            return

        quote = '\n- - - - - - - - - - - - - - -\n'
        if not msg['IsAt'] or not quote in msg['Content']:
            return
        content = msg['Content'].split(quote)
        name=msg['User']['Self']['NickName']
        if not name:
            name=msg['User']['Self']['DisplayName']
        prompt = content[-1][len(name)+1:]
        query = content[0][len(msg['ActualNickName'])+1:]
        title=''
        if '[Link]' in msg['Content'] or '[链接]' in msg['Content']:
            title = self.extractWxTitle(msg['Content'])
            query=self.ripPost(title)
        if query is not None:
            thread_pool.submit(self._do_send_group,query,msg,title,prompt)

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
                query = self.conf.get("character_desc", "") + prompt + '\n『%s\n』'%query
            if len(prompt)<4 or len(query)>2000:
                query = query +'\nTL;DR;'
            reply_text = self.chatBot.reply(query,context)
            if reply_text:
                if title!='':
                    self.posts.at[title,'Summary']=reply_text
                    self.posts.to_csv(self.csvfile,index_label='FileName')
                self.send(self.conf.get("single_chat_reply_prefix") + reply_text, reply_user_id)
                
        except Exception as e:
            logging.exception(e)
            self.waiting = False

    def _do_send_group(self,query,msg,title,prompt):
        if not query:
            return
        if title !='' and title in self.posts.index and self.posts.loc[title]['Summary'] != '' and prompt=='':
            query = self.posts.loc[title]['Summary'].split('[ChatGPT]')[-1]
            self.send(query, msg['User']['UserName'])
            return
        context = dict()
        context['from_user_id'] = msg['ActualUserName']
        query = self.conf.get("character_desc", "") + prompt + '\n『%s\n』'%query
        if len(prompt) < 4 or len(query) > 2000:
            query = query + '\nTL;DR;'
        reply_text = self.chatBot.reply(query, context)
        reply_text = '@' + msg['ActualNickName'] + ' ' + reply_text.strip()
        if reply_text:
            if title != '':
                self.posts.at[title, 'Summary'] = reply_text
                self.posts.to_csv(self.csvfile, index_label='FileName')
            self.send(reply_text, msg['User']['UserName'])
        

    def check_prefix(self, content, prefix_list):
        for prefix in prefix_list:
            if prefix in content:
                return prefix
        return None

    def dealWxUrl(self,rawurl:str):
        if 'mp.weixin.qq.com' not in rawurl:
            return rawurl
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
        row=self.posts.loc[filename]
        res = requests.get(row['Url'])

        soup = BeautifulSoup(res.text, "html.parser")
        for s in soup(['script', 'style']):
            s.decompose()
        queryText=soup.get_text(separator="\n")

        if 'mp.weixin.qq.com' in row['Url']:
            query1 = [x.get_text(separator='\n') for x in soup.find_all('section')]
            query2 = [x.get_text(separator='\n') for x in soup.find_all('p')]
            if len(''.join(query2)) > len(''.join(query1)):
                query1 = query2
            if len('\n'.join(query1)) == 0:
                queryText = re.sub(r'\\x[0-9a-fA-F]{2}', '',
                                   soup.find('meta', {'name': 'description'}).attrs['content'])
            else:
                query1 = '\n'.join(query1).split('\n')
                query = list(set(query1))
                query.sort(key=query1.index)
                queryText = '\n'.join(query)

        return self.dealText(queryText)


    def dealText(self,queryText):
        if len(queryText) <= 2024:
            return queryText
        query = queryText.split('\n')

        def checkIndex(text: str):
            startString = '一,二,三,四,五,六,七,八,九,首先,其次,再次,然后,最后'
            ch_punc = u"[\u3002\uff1b\uff0c\uff1a\u201c\u201d\uff08\uff09\u3001\uff1f\u300a\u300b]"
            if text[0] in startString or text[:2] in startString:
                return True
            elif text[0].isdigit() and (text[1] in string.punctuation or text[1] in ch_punc):
                return True
            else:
                return False

        bullets = [x for x in query if len(x) >= 2 and checkIndex(x) and x not in query]
        bulletsLen = len('\n'.join(bullets))
        query1 = queryText[:1200 - int(bulletsLen / 2)].split('\n')[:-1]
        query1.extend(bullets)
        query1 = [x for x in query1 if x not in queryText[-1200 + int(bulletsLen / 2):]]
        query1.extend(queryText[-1200 + int(bulletsLen / 2):].split('\n')[1:])
        query1 = [x.strip() for x in query1 if len(x.strip()) >= 2]
        query = list(set(query1))
        query.sort(key=query1.index)
        queryText = '\n'.join(query).replace('。\n', '-#$RT$#-').replace('\n', '').replace('-#$RT$#-', '\n')
        return queryText

    def ripBili(self,bvUrl):
        def bili_player_list(bvid):
            url = 'https://api.bilibili.com/x/player/pagelist?bvid=' + bvid
            response = requests.get(url)
            cid_list = [x['cid'] for x in response.json()['data']]
            return cid_list

        def bili_subtitle_list(bvid, cid):
            url = f'https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}'
            response = requests.get(url,cookies={'SESSDATA': 'abf9c486%2C1693408321%2Ca2887%2A32'})
            subtitles = response.json()['data']['subtitle']['subtitles']
            if subtitles:
                return ['https:' + x['subtitle_url'] for x in subtitles]
            else:
                return []

        def bili_subtitle(bvid, cid):
            subtitles = bili_subtitle_list(bvid, cid)
            if subtitles:
                response = requests.get(subtitles[0])
                if response.status_code == 200:
                    body = response.json()['body']
                    return body
            return []

        soup = BeautifulSoup(requests.get(bvUrl).text, 'html.parser')
        bvid = soup.find('meta', {'itemprop': 'url'})['content'].split('/')[-2]
        query=bili_subtitle(bvid, bili_player_list(bvid)[0])

        return '\n'.join(x['content'] for x in query)