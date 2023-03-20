from poe import poeBot
from commonTools import *

with open('config.json') as fr:
    conf = json.loads(fr.read())
    bot=poeBot(conf)
    bot.clear_context()
    print(bot.reply('自我介绍一下'))