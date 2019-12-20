from vk_botting import Cog, command
from random import choice
import json
from bs4 import BeautifulSoup


class Procrastinate(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_random_film(self):
        res = await self.bot.general_request('https://www.kinopoisk.ru/chance/?item=true&not_show_rated=false&count=1&min_years=2000&count=5')
        films = []
        for film in res:
            soup = BeautifulSoup(film, features='lxml')
            link = f'https://www.kinopoisk.ru{soup.meta["content"]}'
            rating = float(soup.find('div', {'class': 'WidgetStars'})['value'])
            films.append((link, rating))
        res = max(films, key=lambda x: x[1])
        return f'Отложи свои дела на пару часов и посмотри этот фильм:\n{res[0]}', res[0]

    async def get_random_article(self):
        links = json.load(open('resources/nplus1.json', 'r'))
        res = choice(links)
        return f'Отложи свои дела на несколько минут и почитай вот эту статью:\n{res}', res

    async def get_random_video(self):
        links = json.load(open('resources/videos.json', 'r'))
        res = choice(links)
        return f'Отложи свои дела на {res[1]} и посмотри это видео:\n{res[0]}', res[0]

    @command(name='прокрастинировать')
    async def proc(self, ctx):
        way = choice([self.get_random_video, self.get_random_article, self.get_random_film])
        msg, link = await way()
        return await ctx.reply(msg, attachment=[link])


def proc_setup(bot):
    bot.add_cog(Procrastinate(bot))
