import datetime
import calendar
import codecs
import dateparser
import dateparser.search
import dateutil
import aiohttp
import locale
import asyncio
import os
from urllib.parse import urlparse
from vk_botting import bot, in_user_list
from rec import speechrec_setup

from credentials import vkNotifBotKey, mosru_mail1, mosru_psw1, mosru_mail2, mosru_psw2, RUParserInfo, weekType, vkPersUserID

locale.setlocale(locale.LC_ALL, 'ru_RU')
commands = ['!Тест', '!Дз <дата> <группа, если нужна>', '!Расписание <дата> <группа>', '!Команды']
group1 = [' группа 1', ' группы 1', ' 1 группа', ' 1 группы', ' первой группы', ' первая группа']
group2 = [' группа 2', ' группы 2', ' 2 группа', ' 2 группы', ' второй группы', ' вторая группа']

counter = 0
dv = False
server = ''
key = ''
failed = 0


async def complete_hw_sequence(email, psw, date):
    session = aiohttp.ClientSession()
    mesh_sid, mesh_token = await get_user(session, email, psw)
    async for task in get_homework(session, mesh_sid, mesh_token, date):
        yield '{} : {}'.format(task['homework']['subject']['name'], task['description'])
    await session.close()


async def get_user(session, email, psw):
    URL = 'https://www.mos.ru/pgu/ru/application/dogm/journal/'
    payload = {
        'login': email,
        'password': psw,
        'alien': 'false'
    }
    result = await session.get(URL, timeout=3)
    result = await session.post(result.url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = result.url.query['token']
    payload = {
        'auth_token': token
    }
    async with session.post('https://dnevnik.mos.ru/lms/api/sessions', json=payload) as result:
        res = await result.json()
        return res['profiles'][0]['id'], token


async def get_homework(session, sid, token, date):
    cookies = {
        'auth_token': token,
        'profile_id': str(sid)
    }
    cookies = aiohttp.cookiejar.BaseCookie(cookies)
    session.cookie_jar.update_cookies(cookies)
    params = {
        'begin_date': date,
        'end_date': date,
        'per_page': 1000
    }
    async with session.get('https://dnevnik.mos.ru/core/api/student_homeworks', params=params, timeout=3) as result:
        res = await result.json()
    grid = []
    for homework in res:
        grid.append(str(homework['homework_entry']['homework']['group_id']))
    params = {
        'group_ids': ','.join(grid),
        'pid': sid
    }
    async with session.get('https://dnevnik.mos.ru/jersey/api/groups', params=params, timeout=3) as groups:
        gps = await groups.json()
    for homework in res:
        homework['homework_entry']['gnum'] = next(group['short_name'] for group in gps if
                                                  group['id'] == homework['homework_entry']['homework']['group_id'])
        if homework['homework_entry']['homework']['date_prepared_for'] == date:
            yield homework['homework_entry']


async def get_subject(session, sid, suid):
    params = {
        'pid': sid,
        'ids': suid
    }
    async with session.get('https://dnevnik.mos.ru/core/api/subjects', params=params, timeout=3) as result:
        res = await result.json()
    return res[0]['name']


async def get_status(session, sid, token):
    cookies = {
        'auth_token': token,
        'profile_id': str(sid)
    }
    cookies = aiohttp.cookiejar.BaseCookie(cookies)
    session.cookie_jar.update_cookies(cookies)
    params = {
        'student_id': sid,
        'pid': sid
    }
    async with session.get('https://dnevnik.mos.ru/notification/api/notifications/status', params=params, timeout=3) as result:
        return await result.json()


async def get_notifs(session, sid):
    params = {
        'student_id': sid,
        'per_page': 1000,
        'page': 1,
        'pid': sid,
        'event_type': 'create_homework'
    }
    async with session.get('https://dnevnik.mos.ru/notification/api/notifications/search', params=params, timeout=3) as result:
        return await result.json()


def parseDate(date):
    words = date.split()
    for i in range(len(words), 0, -1):
        date = ''
        for l in range(i):
            date += words[l] + ' '
        try:
            return [date, dateutil.parser.parse(date, parserinfo=RUParserInfo(), dayfirst=True)]
        except ValueError:
            parsed = dateparser.parse(date, settings={'PREFER_DATES_FROM': 'future', 'DATE_ORDER': 'DMY'})
            if parsed is not None:
                return [date, parsed]
    return 'Неверный формат даты'


def parseGroup(data):
    if data.endswith(' 1'):
        return '1'
    if data.endswith(' 2'):
        return '2'
    if any(first in data for first in group1):
        return '1'
    if any(second in data for second in group2):
        return '2'
    return '3'


async def getHomework(date, group):
    searchdate = date.strftime('%d.%m.%Y')
    formatdate = date.strftime("%a, %d %b %Y")
    msg = 'ДЗ на ' + formatdate
    hwf = []
    if group == '1':
        msg += ' для группы 1:\n'
        async for ent in complete_hw_sequence(mosru_mail1, mosru_psw1, searchdate):
            hwf.append(ent + ' (1)')
    elif group == '2':
        msg += ' для группы 2:\n'
        async for ent in complete_hw_sequence(mosru_mail2, mosru_psw2, searchdate):
            hwf.append(ent + ' (2)')
    else:
        msg += ':\n'
        async for ent in complete_hw_sequence(mosru_mail1, mosru_psw1, searchdate):
            hwf.append(ent + ' (1)')
        async for ent in complete_hw_sequence(mosru_mail2, mosru_psw2, searchdate):
            if ent + ' (1)' not in hwf:
                ent += ' (2)'
                hwf.append(ent)
            else:
                hwf[hwf.index(ent + ' (1)')] = hwf[hwf.index(ent + ' (1)')][:-4]
    if not hwf:
        return 'Нет ДЗ на ' + formatdate
    for i in range(len(hwf)):
        hwf[i] = '{}. {}'.format(i+1, hwf[i])
    return msg + '\n'.join(hwf)


def getSchedule(date, group):
    formatdate = date.strftime("%a, %d %b %Y")
    if date.weekday() > 4:
        return formatdate + ' - выходной'
    week = date.isocalendar()[1]
    if week >= len(weekType) or weekType[week] == -1:
        return 'Нет информации на ' + formatdate
    if weekType[week] == 0:
        return formatdate + ' - выходной'
    msg = 'Расписание на ' + formatdate
    formatweekday = calendar.day_name[date.weekday()].lower()
    if group == '3':
        msg += ':\n'
        for i in range(2):
            sched = codecs.open(r'schedule/{}_{}_{}.txt'.format(formatweekday, weekType[week], i + 1), 'r',
                                'utf-16').read()
            msg += 'Для группы {}:\n{}\n'.format(i + 1, sched)
        return msg
    data = codecs.open(r'schedule/' + formatweekday + '_' + str(weekType[week]) + '_' + group + '.txt', 'r',
                       'utf-16').read()
    msg += ' для группы {}:\n{}'.format(group, data)
    return msg


async def checkStatus():
    session = aiohttp.ClientSession()
    fin = []
    mesh_sid, mesh_token = await get_user(session, mosru_mail1, mosru_psw1)
    res = await get_status(session, mesh_sid, mesh_token)
    if res:
        notifs = await get_notifs(session, mesh_sid)
        for notif in notifs:
            ndt = datetime.datetime.strptime(notif['datetime'][:19], '%Y-%m-%d %H:%M:%S')
            if ndt > datetime.datetime.today()-datetime.timedelta(seconds=301):
                notif['sname'] = await get_subject(session, mesh_sid, notif['subject_id'])
                notif['gn'] = '1'
                fin.append(notif)
    await session.close()
    session = aiohttp.ClientSession()
    mesh_sid, mesh_token = await get_user(session, mosru_mail2, mosru_psw2)
    res = await get_status(session, mesh_sid, mesh_token)
    if res:
        notifs = await get_notifs(session, mesh_sid)
        for notif in notifs:
            ndt = datetime.datetime.strptime(notif['datetime'][:19], '%Y-%m-%d %H:%M:%S')
            if ndt > datetime.datetime.today() - datetime.timedelta(seconds=301):
                notif['sname'] = await get_subject(session, mesh_sid, notif['subject_id'])
                notif['gn'] = '2'
                fin.append(notif)
    await session.close()
    return fin


async def vkMsg(peer_id, msg=None, attach=None):
    payload = {'access_token': vkNotifBotKey, 'v': '5.80',
               'message': msg,
               'peer_id': peer_id,
               'attachment': attach}
    async with aiohttp.ClientSession() as session:
        r = await session.get('https://api.vk.com/method/messages.send', params=payload)
        return r.json()


async def vkUpload(peer_id, file, typ='doc'):
    payload = {'access_token': vkNotifBotKey, 'v': '5.101',
               'type': typ,
               'peer_id': peer_id}
    async with aiohttp.ClientSession() as session:
        r = await session.get('https://api.vk.com/method/docs.getMessagesUploadServer', params=payload)
        r = await r.json()
        imurl = r['response']['upload_url']
        files = {'file': open(file, 'rb')}
        r = await session.post(imurl, files=files)
        r = await r.json()
        filedata = r['file']
        payload = {
            'access_token': vkNotifBotKey, 'v': '5.101',
            'file': filedata,
            'title': os.path.splitext(file)[0]
        }
        r = await session.get('https://api.vk.com/method/docs.save', params=payload)
        r = await r.json()
        doc = r['response']
    parsed = urlparse(doc[doc['type']]['url'])
    return parsed.path[1:]


async def check():
    while True:
        try:
            await asyncio.sleep(300)
            prid = vkPersUserID if dv else 2000000001
            status = await checkStatus()
            for i in range(len(status)):
                new = status[i]
                found = False
                for tmp in status[i + 1:]:
                    if new['sname'] + new['new_hw_description'] + new['new_hw_description'] == tmp['sname'] + tmp['new_hw_description'] + tmp['new_hw_description']:
                        del status[status.index(tmp)]
                        if new['gn'] != tmp['gn']:
                            found = True
                            ndt = datetime.datetime.strptime(new['new_date_prepared_for'][:10], '%Y-%m-%d')
                            if ndt > datetime.datetime.today():
                                await vkMsg(prid, 'Новое дз для обеих групп на {} по {}: {}'.format(datetime.datetime.strptime(new['new_date_prepared_for'][:10], '%Y-%m-%d').strftime(
                                    '%a, %d %b %Y'), new['sname'], new['new_hw_description']))
                                break
                if not found:
                    ndt = datetime.datetime.strptime(new['new_date_prepared_for'][:10], '%Y-%m-%d')
                    if ndt > datetime.datetime.today():
                        await vkMsg(prid, 'Новое дз для группы {} на {} по {}: {}'.format(new['gn'], ndt.strftime(
                            '%a, %d %b %Y'), new['sname'], new['new_hw_description']))
        except Exception as e:
            print(f'Ошибка: {e}')


nbot = bot.Bot(command_prefix=bot.when_mentioned_or('!'), case_insensitive=True)


@nbot.listen()
async def on_ready():
    print(f'Logged in as {nbot.group.name}')
    nbot.loop.create_task(check())
    speechrec_setup(nbot)


@nbot.command(name='тест')
async def test(ctx):
    return await ctx.reply('Тестовое сообщение')


@nbot.command(name='дз')
async def hw(ctx, *, text):
    text = text.lower()
    text = text.replace('!дз ', '')
    group = parseGroup(text)
    if text.endswith(' 1') or text.endswith(' 2'):
        text = text[:-2]
    date = parseDate(text)
    if date == 'Неверный формат даты':
        return await ctx.reply('Я не понимаю этот формат даты. Чтобы все точно сработало, используйте формат дд.мм.гг')
    msg = await getHomework(date[1], group)
    return await ctx.reply(msg)


@nbot.command(name='расписание', aliases=['р'])
async def sched(ctx, *, text=None):
    if not text:
        return await ctx.reply(attachment='photo-179049108_457239024')
    text = text.lower()
    group = parseGroup(text)
    if text.endswith(' 1') or text.endswith(' 2'):
        text = text[:-2]
    date = parseDate(text)
    if date == 'Неверный формат даты':
        msg = 'Я не понимаю этот формат даты. Чтобы все точно сработало, используйте формат дд.мм.гг'
    else:
        msg = getSchedule(date[1], group)
    return await ctx.reply(msg)


@nbot.command(name='команды')
async def get_commands(ctx):
    msg = 'Команды:\n'
    for i, command in enumerate(commands):
        msg += f'{i+1}: {command}\n'
    await ctx.reply(msg)


@nbot.command()
@in_user_list(vkPersUserID)
async def do(ctx):
    global dv
    dv = not dv
    return await ctx.reply(':)')


@nbot.command(name='Прокрастинировать')
async def proc(ctx):
    global counter
    counter += 1
    return await ctx.reply(str(counter))


nbot.run(vkNotifBotKey)
