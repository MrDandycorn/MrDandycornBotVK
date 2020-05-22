from vk_botting import Bot, when_mentioned_or_pm_or
from rec import speechrec_setup
from procrastinate import proc_setup

from credentials import vk_notification_bot_key

nbot = Bot(command_prefix=when_mentioned_or_pm_or('!'), case_insensitive=True)


@nbot.listen()
async def on_ready():
    print(f'Logged in as {nbot.group.name}')
    speechrec_setup(nbot)
    proc_setup(nbot)


@nbot.command(name='тест')
async def test(ctx):
    return await ctx.reply('Тестовое сообщение')


nbot.run(vk_notification_bot_key)
