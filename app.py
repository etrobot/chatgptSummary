import logging

from wechat import *

class test():
    def __init__(self):
        with open('config.json') as fr:
            self.conf = json.loads(fr.read())

    def getConf(self):
        print(self.conf.get('single_chat_prefix'))



if __name__ == "__main__":
    wechat = weChat()
    wechat.startup()
