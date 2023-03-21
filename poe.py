import json
import re

import requests
from requests.adapters import HTTPAdapter
import time, logging


class poeBot():

    def __init__(self, conf: dict):

        self.url = 'https://www.quora.com/poe_api/gql_POST'
        self.headers  = {
            'Host': 'www.quora.com',
            'Accept': '*/*',
            'apollographql-client-version': '1.1.6-65',
            'Accept-Language': 'en-US,en;q=0.9',
            'User-Agent': 'Poe 1.1.6 rv:65 env:prod (iPhone14,2; iOS 16.2; en_US)',
            'apollographql-client-name': 'com.quora.app.Experts-apollo-ios',
            'Connection': 'close',
            'Content-Type': 'application/json',
            'Cookie': conf.get('Cookie'),
        }
        self.proxies = {
            'http': conf.get('proxy'),
            'https': conf.get('proxy'),
        }
        self.headers['Quora-Formkey']=self.getFormkey()
        self.ss=requests.session()
        self.bot = conf.get('llm','capybara')
        self.chat_id = self.load_chat_id_map()
        self.clear_context()
        self.state=None

    def getFormkey(self):
        pattern=r'formkey": "(.*?)", "errorSamplingRate'
        match = re.search(pattern,  requests.get('https://www.quora.com',headers=self.headers,proxies=self.proxies).text)
        if match:
            return match.group(1)

    def load_chat_id_map(self):
        data = {
            'operationName': 'ChatViewQuery',
            'query': 'query ChatViewQuery($bot: String!) {\n  chatOfBot(bot: $bot) {\n    __typename\n    ...ChatFragment\n  }\n}\nfragment ChatFragment on Chat {\n  __typename\n  id\n  chatId\n  defaultBotNickname\n  shouldShowDisclaimer\n}',
            'variables': {
                'bot': self.bot
            }
        }
        response = requests.post(self.url, headers=self.headers, json=data, proxies=self.proxies)
        return response.json()['data']['chatOfBot']['chatId']

    def send_message(self, message):
        if self.state == "incomplete":
            return
        data = {
            "operationName": "AddHumanMessageMutation",
            "query": "mutation AddHumanMessageMutation($chatId: BigInt!, $bot: String!, $query: String!, $source: MessageSource, $withChatBreak: Boolean! = false) {\n  messageCreate(\n    chatId: $chatId\n    bot: $bot\n    query: $query\n    source: $source\n    withChatBreak: $withChatBreak\n  ) {\n    __typename\n    message {\n      __typename\n      ...MessageFragment\n      chat {\n        __typename\n        id\n        shouldShowDisclaimer\n      }\n    }\n    chatBreak {\n      __typename\n      ...MessageFragment\n    }\n  }\n}\nfragment MessageFragment on Message {\n  id\n  __typename\n  messageId\n  text\n  linkifiedText\n  authorNickname\n  state\n  vote\n  voteReason\n  creationTime\n  suggestedReplies\n}",
            "variables": {
                "bot": self.bot,
                "chatId": self.chat_id,
                "query": message,
                "source": None,
                "withChatBreak": False
            }
        }
        _rspn = self.ss.request("POST",url=self.url, headers=self.headers, json=data, proxies=self.proxies,timeout=5)
        self.state = "incomplete"
        time.sleep(2)
        return self.get_latest_message()
        # logging.getLogger('log').debug(rsp.text)

    def clear_context(self):
        data = {
            "operationName": "AddMessageBreakMutation",
            "query": "mutation AddMessageBreakMutation($chatId: BigInt!) {\n  messageBreakCreate(chatId: $chatId) {\n    __typename\n    message {\n      __typename\n      ...MessageFragment\n    }\n  }\n}\nfragment MessageFragment on Message {\n  id\n  __typename\n  messageId\n  text\n  linkifiedText\n  authorNickname\n  state\n  vote\n  voteReason\n  creationTime\n  suggestedReplies\n}",
            "variables": {
                "chatId": self.chat_id
            }
        }
        self.ss.mount('https://', HTTPAdapter(max_retries=3))
        _rspn = self.ss.request("POST",url=self.url, headers=self.headers, json=data, proxies=self.proxies,timeout=5)

    def get_latest_message(self):
        data = {
            "operationName": "ChatPaginationQuery",
            "query": "query ChatPaginationQuery($bot: String!, $before: String, $last: Int! = 10) {\n  chatOfBot(bot: $bot) {\n    id\n    __typename\n    messagesConnection(before: $before, last: $last) {\n      __typename\n      pageInfo {\n        __typename\n        hasPreviousPage\n      }\n      edges {\n        __typename\n        node {\n          __typename\n          ...MessageFragment\n        }\n      }\n    }\n  }\n}\nfragment MessageFragment on Message {\n  id\n  __typename\n  messageId\n  text\n  linkifiedText\n  authorNickname\n  state\n  vote\n  voteReason\n  creationTime\n}",
            "variables": {
                "before": None,
                "bot": self.bot,
                "last": 1
            }
        }
        replyText=None
        while self.state == "incomplete":
            _rspn = self.ss.request("POST", url=self.url, headers=self.headers, json=data, proxies=self.proxies,
                                    timeout=3)
            response_json = _rspn.json()
            # logging.getLogger('itchat').info(response_json)
            replyText = response_json['data']['chatOfBot']['messagesConnection']['edges'][-1]['node']['text']
            self.state = response_json['data']['chatOfBot']['messagesConnection']['edges'][-1]['node']['state']
            if self.state == "complete":
                return replyText
            logging.getLogger('itchat').debug(self.state)
            time.sleep(2)
        return replyText

    def reply(self, message: str, context=None):
        replyText = self.send_message(message)
        # logging.getLogger('itchat').debug(f"{self.bot} : {replyText}")
        if context is not None:
            with open('./user_session.json', 'w', encoding='utf-8') as f:
                json.dump(context, f)
        return replyText
