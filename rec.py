from vk_botting import cog
from vk_botting import AudioMessage
import aiohttp
import time
import asyncio
import json
import jwt
import aioboto3

from credentials import yandex_cloud_folder_id, yandex_service_account_id, yandex_service_key_id, aws_key_id, aws_secret_key


def get_jwt():
    with open("private_key.pem", 'r') as private:
        private_key = private.read()
    now = int(time.time())
    payload = {
        'aud': 'https://iam.api.cloud.yandex.net/iam/v1/tokens',
        'iss': yandex_service_account_id,
        'iat': now,
        'exp': now + 360
    }
    encoded_token = jwt.encode(
        payload,
        private_key,
        algorithm='PS256',
        headers={'kid': yandex_service_key_id})
    return encoded_token


async def get_bytes(url):
    async with aiohttp.ClientSession() as session:
        req = await session.get(url)
        audio_bytes = await req.read()
    return audio_bytes


async def upload_file(url):
    audio_bucket_url = 'https://storage.yandexcloud.net/speechrecognition/'
    conf = {
        'service_name': 's3',
        'endpoint_url': 'https://storage.yandexcloud.net',
        'aws_access_key_id': aws_key_id,
        'aws_secret_access_key': aws_secret_key
    }
    async with aioboto3.client(**conf) as s3:
        name = 'audio{}.ogg'.format(time.time())
        body = await get_bytes(url)
        await s3.put_object(Bucket='speechrecognition', Key=name, Body=body, StorageClass='COLD')
    return name, audio_bucket_url+name


async def delete_file(name):
    conf = {
        'service_name': 's3',
        'endpoint_url': 'https://storage.yandexcloud.net',
        'aws_access_key_id': aws_key_id,
        'aws_secret_access_key': aws_secret_key
    }
    async with aioboto3.client(**conf) as s3:
        forDeletion = [{'Key': name}]
        await s3.delete_objects(Bucket='speechrecognition', Delete={'Objects': forDeletion})


async def get_serv_iam():
    auth_url = 'https://iam.api.cloud.yandex.net/iam/v1/tokens'
    jwtoken = get_jwt()
    data = {
        'jwt': jwtoken.decode('utf-8')
    }
    data = json.dumps(data)
    async with aiohttp.ClientSession() as session:
        req = await session.post(auth_url, data=data)
        req = await req.json()
    iam = req['iamToken']
    return iam


async def speech_to_text_short(url):
    audio = await get_bytes(url)
    iam_token = await get_serv_iam()
    speech_url = 'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize'
    params = {
        'lang': 'ru-RU',
        'topic': 'general',
        'profanityFilter': 'false',
        'format': 'oggopus',
        'folderId': yandex_cloud_folder_id
    }
    headers = {
        'Authorization': 'Bearer '+iam_token
    }
    async with aiohttp.ClientSession() as session:
        r = await session.post(speech_url, params=params, headers=headers, data=audio)
        r = await r.json()
    return r['result']


async def speech_to_text_long(url):
    iam_token = await get_serv_iam()
    speech_url = 'https://transcribe.api.cloud.yandex.net/speech/stt/v2/longRunningRecognize'
    data = {
        "config": {
            "specification": {
                "languageCode": "ru-RU",
                "profanityFilter": "false",
                "audioEncoding": "OGG_OPUS"
            },
            "folderId": yandex_cloud_folder_id
        },
        "audio": {
            "uri": url
        }
    }
    data = json.dumps(data)
    headers = {
        'Authorization': 'Bearer ' + iam_token
    }
    async with aiohttp.ClientSession() as session:
        res = await session.post(speech_url, headers=headers, data=data)
        res = await res.json()
    op_id = res.get('id', None)
    if op_id is None:
        return 'Внутренняя ошибка сервера'
    check_url = 'https://operation.api.cloud.yandex.net/operations/' + op_id
    while True:
        await asyncio.sleep(2)
        async with aiohttp.ClientSession() as session:
            res = await session.get(check_url, headers=headers)
            res = await res.json()
        status = res.get('done', False)
        if status:
            variants = res['response']['chunks']
            if variants:
                resulting_text = ''
                for variant in variants:
                    resulting_text += variant['alternatives'][0]['text'] + ' '
                return resulting_text
            return 'Я не понимаю, что сказал этот пользователь'


class speechrec(cog.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def process(self, msg):
        res = []
        attachments = msg.attachments
        if attachments:
            for attachment in attachments:
                if attachment.__class__ is AudioMessage:
                    async with msg.typing():
                        link = attachment.link_ogg
                        name, audio_url = await upload_file(link)
                        message = await speech_to_text_long(audio_url)
                        await delete_file(name)
                        res.append(message)
        fwded = msg.fwd_messages
        if fwded:
            for fwd in fwded:
                t = await self.process(fwd)
                res += t
        return res

    @cog.Cog.listener()
    async def on_message_new(self, msg):
        msges = await self.process(msg)
        if len(msges) == 1:
            reply = msges[0]
        else:
            reply = ''
            for num, res in enumerate(msges):
                reply += f'{num + 1}. {res}\n'
        if reply:
            return await msg.reply(reply)


def speechrec_setup(bot):
    bot.add_cog(speechrec(bot))
