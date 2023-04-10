import json
import string,logging
import re
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
import pandas as pd
from bs4 import BeautifulSoup
import requests
class posts():
    def __init__(self):
        self.filename='./articles.csv'
        self.df=pd.read_csv(self.filename,index_col='FileName',keep_default_na=False)

    def update(self,key,field,content):
        self.df.at[key, field] = content
        self.df.to_csv(self.filename,index_label='FileName')

class conf():
    def __init__(self):
        with open('config.json','rb') as fr:
            self.conf = json.loads(fr.read())

    def get(self,key:str,default=None):
        return self.conf.get(key,default)

def check_prefix(content:str, prefix_list):
    for prefix in prefix_list:
        if content.startswith(prefix):
            return prefix
    return None
def extractWxTitle(txt):
    pattern = r'\[Link\]\s+(.*?)"\n- - - - - - - - - - - - - - -\n'
    if '[链接]' in txt:
        pattern = r'\[链接\]+(.*?)」\n- - - - - - - - - - - - - - -\n'
    match = re.search(pattern, txt)
    if match:
        log.debug(match.group(1))
        return match.group(1)

def dealWxUrl(rawurl:str):
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

def ripPost(filename,posts):
    row = posts.loc[filename]
    res = requests.get(row['Url'])
    if '23.tv' in row['Url']:
        return dealText(ripBili(row['Url']))

    soup = BeautifulSoup(res.text, "html.parser")
    for s in soup(['script', 'style']):
        s.decompose()
    queryText = soup.get_text(separator="\n")

    if 'mp.weixin.qq.com' in row['Url']:
        if conf.get( 'mp.weixin.qq.com' ):
            soup=soup.find(id=conf.get( 'mp.weixin.qq.com' ))
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
            queryText = '《%s》'%filename+'\n'.join(query)

    return dealText(queryText)


def dealText(queryText:str):
    if len(queryText) <= 1800:
        return queryText
    query = queryText.split('\n')

    def checkIndex(text: str):
        ch_punc = u"[\u3002\uff1b\uff0c\uff1a\u201c\u201d\uff08\uff09\u3001\uff1f\u300a\u300b]"
        if text[0] in '一,二,三,四,五,六,七,八,九' or text[:2] in '首先,其次,再次,然后,最后,结论,总结,综上':
            return True
        elif text[0].isdigit() and (text[1] in string.punctuation or text[1] in ch_punc):
            return True
        else:
            return False

    keyPoints = [x for x in query if len(x) >= 2 and checkIndex(x)]
    keyPointsLen = len('\n'.join(keyPoints))
    query1 = queryText[:840 - int(keyPointsLen / 2)].split('\n')[:-1]
    query1.extend(keyPoints)
    query1 = [x for x in query1 if x not in queryText[-1200 + int(keyPointsLen / 2):]]
    query1.extend(queryText[-1000 + int(keyPointsLen / 2):].split('\n')[1:])
    query1 = [x.strip() for x in query1 if len(x.strip()) >= 2]
    query = list(set(query1))
    query.sort(key=query1.index)
    for item in query:
        if item in keyPoints:
            query[query.index(item)]='-#$RT$#-'+item
    queryText = '\n'.join(query).replace('。\n', '-#$RT$#-').replace('\n', '').replace('-#$RT$#-', '\n')
    log.debug('Text Length: %s' % len(queryText))
    return queryText


def ripBili(bvUrl):
    def bili_player_list(bvid):
        url = 'https://api.bilibili.com/x/player/pagelist?bvid=' + bvid
        response = requests.get(url)
        cid_list = [x['cid'] for x in response.json()['data']]
        return cid_list

    def bili_subtitle_list(bvid, cid):
        url = f'https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}'
        sessdata=conf.get('SESSDATA')
        if conf.get('vika.cn'):
            vikaUrl = 'https://api.vika.cn/fusion/v1/datasheets/dstMiuU9zzihy1LzFX/records?viewId=viwoAJhnS2NMT&fieldKey=name'
            vikaCache = json.loads(requests.get(vikaUrl, headers={'Authorization': conf.get("vika.cn")}).text)['data']['records']
            sessdata=[x['fields']['value'] for x in vikaCache if x['recordId']=='recRh258ujPiq'][0]
        response = requests.get(url, cookies={'SESSDATA':sessdata })
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
    query = bili_subtitle(bvid, bili_player_list(bvid)[0])

    return '\n'.join(x['content'] for x in query)

def is_contain_chinese(check_str):
    for ch in check_str:
        if u'\u4e00' <= ch <= u'\u9fff':
            return True
    return False

thread_pool = ThreadPoolExecutor(max_workers=8)
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
posts=posts()
conf=conf()