# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import time
import os
import requests
import datetime
import sys
import hashlib
import logging
import traceback
import re
from bs4 import BeautifulSoup
import lxml.html as html
import requests_random_user_agent


MAIN_URL = 'https://olimp.com/betting'
DOMAIN = MAIN_URL.split('/')[2:-1]
DOMAIN = ''.join(DOMAIN)

bk_name = 'olimp_com'
timeout = 30
restart_time_pars = 10


def get_html(session, url, headers):
    '''
    получение контента веб-страницы
    '''
    response = session.get(url)
    response.encoding = 'utf-8'
    if response.status_code != 200:
        print('Неудачное соединение', f'{response.status_code}')
    else:
        print('-------------------')
        return response


def get_main_content(response):
    '''
    # получение информации о всех играх в лайве
    '''
    htmlBODY = html.fromstring(response.text)
    elem = htmlBODY.xpath("//*[contains(@class,'liveMainSport')]")
    sportArr = {}
    for sportEl in elem:
        sport_id = sportEl.get('data-sport')
        sport_name = sportEl.text_content()
        sport_name = sport_name.replace('  ', '')
        sport_name = sport_name.replace('\n', '')
        sport_name = sport_name.strip()
        sport_name = sport_name.split(' (')[0]
        sportArr[sport_id] = sport_name
    # print(sportArr)
    elem = htmlBODY.xpath("//*[contains(@class,'forLiveFilter')]")
    gamerArr = {}
    gamer_arr_list = []
    for gamerEl in elem:
        sport_id = gamerEl.get('data-sport')
        if sport_id in sportArr:
            gamer_name = gamerEl.xpath(".//a[contains(@class,'l-name-tab')]")
            if len(gamer_name) > 0:
                gamer_id = gamer_name[0].get('id')
                gamer_id = gamer_id.replace('match_live_name_', '')
                gamer_name = gamer_name[0].text_content()
                gamer_name = gamer_name.replace('  ', '')
                gamer_name = gamer_name.replace('\n', '')
                gamer_name = gamer_name.strip()

                href = gamerEl.xpath(
                    ".//a[contains(@class,'l-name-tab')]/@href")[0]
                game_url = f'https://{DOMAIN}/{href}'

                scoreTime = gamerEl.xpath(
                    ".//font[contains(@class,'l-name-tab')]")
                if len(scoreTime) > 0:
                    scoreTime = scoreTime[0].text_content()
                else:
                    scoreTime = ''
                gamerArr = {
                    'sport_id': sport_id,
                    'gamer_id': gamer_id,
                    'sport': sportArr[sport_id],
                    'name': gamer_name,
                    'scoreTime': scoreTime,
                    'game_url': game_url
                }
                gamer_arr_list.append(gamerArr)
    print(gamer_arr_list)
    return gamer_arr_list


def game_page_content(response):
    '''
    получение всей информации по отдельной игре.
    '''
    soup = BeautifulSoup(response.text, 'lxml')
    koef_table = soup.find('table', class_='koeftable2')

    try:
        start_g = koef_table.find('td').get_text()
        started_at = re.sub(r'[^\d\.\:\ ]', '', start_g)  # время начала игры
    except Exception:
        started_at = 'Null'

    try:
        game_id = koef_table.find('a', class_='fav').get(
            'data-favid').split(':')[-1]  # id игры
    except Exception:
        game_id = 'Null'

    try:
        liga_info_list = soup.find(
            'td', class_='ishodRollTitle').get_text().split('.')[1:]
        liga_info = ''.join(liga_info_list).strip()
        liga_info = liga_info.replace('\n', '')  # название лиги
    except Exception:
        liga_info = 'Null'

    try:
        liga_id = soup.find('a', class_='show_all_odds').get('data-champ_id')
    except Exception:
        liga_id = 'Null'

    try:
        score = koef_table.find('div', class_='gameNameLine').find(
            'font', class_='txtmed').get_text()  # текущий счет
    except Exception:
        score = 'Null'

    if '"' in score:
        time_ = score.split('"')[0].split()[-1]
        time_game = f'{time_} Мин'  # сколько времени в игре прошло
    elif ('PAUSE' in score) or ('Перерыв' in score):
        time_game = 'Break'
    elif ('Матч не начался' in score):
        time_game = 'Not start'
    elif ('Матч завершен' in score):
        time_game = 'Closed'
    else:
        time_game = 'Null'

    try:
        # название игры
        gamer_name = koef_table.find('div', class_='gameNameLine').find('font', class_='m').find('span', id=f'match_live_name_{game_id}').get_text().strip()
        gamer1 = gamer_name.split(' - ')[0].strip()  # первый игрок
        gamer2 = gamer_name.split(' - ')[1].strip()  # второй игрок
    except Exception:
        gamer_name = 'Null'
        gamer1 = "Null"
        gamer2 = 'Null'

    try:
        koef_spans = koef_table.find('div', id=f'odd{game_id}').find_all('span', class_='googleStatIssue')

        koef_list_src = []  # список всех доступных коэффициентов матча
        for span in koef_spans:
            k_name = span.find(
                'span', class_='googleStatIssueName').get_text().strip()
            k_name = k_name.replace('\xa0', '')  # название коэффициента
            k_res = span.find('span', id='googleStatKef').get_text()  # кэф

            data_k = {
                k_name: k_res
            }
            koef_list_src.append(data_k)
        koef_list = get_pair_in_dict(koef_list_src)
    except Exception:
        koef_list = []

    data = {

        'started_at': started_at,
        'champ': liga_info,
        'liga_id': liga_id,
        'game_id': game_id,
        'time_game': time_game,
        'score': score,
        'gamer_name': gamer_name,
        'gamer1': gamer1,
        'gamer2': gamer2,
        'koef_list': koef_list,

    }

    return data


def get_pair_in_dict(koef_list):
    p1 = re.compile(r'.*мен')
    p2 = re.compile(r'(?<=мен)(\W+\w+.\d+|\W+\w+)\s(.*бол)')
    p3 = re.compile(r'(?<=мен)(\W+\w+.\d+|\W+\w+)')
    p4 = re.compile(r'(?<=бол)(\W+\w+.\d+|\W+\w+)')

    new_koef_list = []
    for dict_ in koef_list:
        for key, value in dict_.items():
            if 'мен' in key and 'бол' in key:
                part1 = p1.search(key)  # получаем первую часть ключа
                part2 = p2.search(key)  # получаем вторую часть ключа
                part3 = p3.search(key)  # получаем значение мен
                part4 = p4.search(key)  # получаем значение бол

                new_koef_list.append(
                    {part1.group(0): str(abs(float(part3.group())))}
                )
                new_koef_list.append(
                    {part2.group(2): str(abs(float(part4.group())))}
                )

            else:
                new_koef_list.append(dict_)
    return new_koef_list


def parsing():
    with requests.Session() as session:
        time1 = datetime.datetime.now()
        user_agent = session.headers
        headers = {
            'content-type': 'application/x-www-form-urlencoded',
            'user-agent': user_agent['User-Agent'],
            'x-requested-with': 'XMLHttpRequest'
        }

        with open('logging.log', 'w'):
            pass

        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler('logging.log')
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.info("Start")

        bk_id = 123123  # тестовое значение

        work = True
        while work:
            try:
                bool_while = True
                while bool_while:
                    response = get_html(
                        session, MAIN_URL, headers=headers
                    )
                    if response:
                        bool_while = False
                    if bool_while:
                        logger.info("ERROR! - No request url: " + MAIN_URL)

                sports = get_main_content(response)
                print(len(sports))

                for sport in sports:
                    '''
                    получение всей инфы по отдельному матчу
                    '''
                    liga_info = {}
                    gamer_info = {}
                    gamer_live = {}
                    sport_id = sport['sport_id']
                    url = sport['game_url']

                    game_info = game_page_content(
                        get_html(
                            session, url, headers=headers
                        )
                    )
                    print('=========')
                    if game_info:
                        bool_while = False
                    if bool_while:
                        logger.info(
                            "ERROR! - No request url: " + sport['game_url']
                        )
                    else:
                        bk_id_liga = game_info['liga_id']
                        liga = game_info['champ']
                        sport_id = str(sport_id)
                        id_liga_hash = hashlib.md5(
                            (str(bk_id_liga) + bk_name).encode('utf-8')
                        ).hexdigest()
                        # словарь liga_info
                        liga_info[id_liga_hash] = {
                            'liga': liga,
                            'sport_id': sport_id,
                            'bk_id': bk_id_liga,
                            'live_is': 1}
                        print(liga_info)

                        game_id = game_info['game_id']
                        gamer1 = game_info['gamer1']
                        gamer2 = game_info['gamer2']
                        gamer_name = game_info['gamer_name']
                        bk_id_gamer1 = 0
                        bk_id_gamer2 = 0
                        started_at = game_info['started_at']
                        time_game = game_info['time_game']
                        score = game_info['score']
                        state = 'Null'
                        link = sport['game_url']

                        id_game_hash = hashlib.md5(
                            (str(game_id) + bk_name).encode('utf-8')
                        ).hexdigest()
                        gamer_info_1 = hashlib.md5(
                            (gamer1 + str(sport_id) + bk_name).encode('utf-8')
                        ).hexdigest()
                        gamer_info_2 = hashlib.md5(
                            (gamer2 + str(sport_id) + bk_name).encode('utf-8')
                        ).hexdigest()

                        if ('УГЛ ' in gamer1) or ('ЖК ' in gamer1) or (' (штанги и перекладины)' in gamer1) or (' (удары в створ)' in gamer1) or (' (офсайды)' in gamer1) or (' (фолы)' in gamer1):
                            pass
                        else:
                            gamer_info[id_game_hash] = {
                                'gamer_id_bk': game_id,
                                'liga_info': id_liga_hash,
                                'bk_id': bk_id,
                                'name': gamer_name,
                                'gamer_info_1': gamer_info_1,
                                'gamer_info_2': gamer_info_2,
                                'time_game': time_game,
                                'score': score,
                                'period': '',
                                'comment': '',
                                'link': link,
                                'started_at': started_at,
                                'created_at': '',
                                'update_at': '',
                                'state': state,
                            }
                            print(gamer_info)

                            koef_list = game_info['koef_list']

                            print(koef_list)
                            time2 = datetime.datetime.now()
                            print(time2 - time1)
            except Exception:
                logger.info(traceback.format_exc())


def main():
    parsing()


if __name__ == '__main__':
    main()
