# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import os
import re
import sys
import json
import time
import random
import hashlib
import pickle
import logging
import requests
import datetime
import traceback
from multiprocessing import Pool, Process
from requests.auth import HTTPBasicAuth, HTTPProxyAuth

bk_name = 'leon_ru'
timeout = 30
restart_time_pars = 4
liga_info, gamer_info, info_koef = {}, {}, {}


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('logging.log')
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_response(session, url, headers, attempts=3):  # +
    '''получение контента веб-страницы'''
    a = attempts
    try:
        response = session.get(url, headers=headers)
        return response
    except Exception as e:
        print('Ошибка при get запросе')
        print(e, type(e))
        if a > 1:
            a -= 1
            time.sleep(1)
            get_response(session, headers, url, a)


def get_info_on_all_sports(response) -> dict:  # +
    '''получение информации о видах спорта'''
    data = response.json()
    sport_arr = {}
    for el in data:
        sport_id = el.get('id')
        sport_name = el.get('name')
        sport_arr[sport_id] = sport_name
    # print(sport_arr)
    return sport_arr


def get_main_content(response) -> list:  # +
    '''получение информации о всех играх в лайве'''
    data = response.json()
    # print(data)
    gamerArr = {}
    gamer_arr_list = []
    for elem in data.get('events'):
        gamer_id = elem.get('id')
        gamer_name = elem.get('name')
        game_slug = elem.get('url')
        liga_id = elem.get('league').get('id')
        gamerArr = {
            'gamer_id': gamer_id,
            'name': gamer_name,
            'liga_id': liga_id,
            'slug': game_slug
        }
        gamer_arr_list.append(gamerArr)
    return gamer_arr_list


def configure_score_and_time(data) -> str:  # +
    """
    Возвращает счет, время матча и комментарий.
    СЧЕТ
    Подгоняем значения под нужный формат.
        Для Тениса и Киберспорта:
        0:0 (0:0, 0:0) 0:0
        # 0:0 это Геймы (0:0 Это Сеты) 0:0 это очки
        Для Баскетбола
        time_game это время, которое осталось играть в четверти
        Для Футбола, Хоккея и Волейбола по аналогии с тенисом
        0:0 (0:0, 0:0)
        # 0:0 это общий счет (0:0 Это счет за тайм)
    :param live:
    :return score: Очки игры в определенном формате
    :return match_time: Время матча, нужны только минуты
    :return comment: "Перерыв", "2-й тайм", "3-й сет"
    """
    score = ""
    comment = ""
    time_game = 'None'
    sport = data.get('league').get('sport').get('name')
    try:
        if (sport == 'Теннис') or (sport == 'Киберспорт'):
            games_score = data.get('liveStatus').get('score')
            sets_score = data.get('liveStatus').get('setScores')
            try:
                current_score = data['liveStatus']['progress']
            except Exception:
                current_score = ''
            score = f'{games_score} ({sets_score}) {current_score}'
            comment = data.get('liveStatus').get('stage')
            if comment == 'Перерыв':
                comment = 'Break'
                time_game = comment
            elif comment == 'В игре':
                comment = 'In play'
                time_game = comment
            elif comment == 'Прелайв':
                comment = 'Prelive'
                time_game = comment
            else:
                time_game = ''
        elif (sport == 'Настольный теннис') or (sport == 'Волейбол'):
            games_score = data.get('liveStatus').get('score')
            sets_score = data.get('liveStatus').get('setScores')
            score = f'{games_score} ({sets_score})'
            comment = data.get('liveStatus').get('stage')
            if comment == 'Перерыв':
                comment = 'Break'
                time_game = comment
            else:
                time_game = ''
        elif (sport == 'Футбол') or (sport == 'Хоккей') or (sport == 'Американский футбол'):
            current_score = data.get('liveStatus').get('score')
            sets_score = data.get('liveStatus').get('setScores')
            score = f"{current_score} ({sets_score})"
            comment = data.get('liveStatus').get('stage')
            if comment == 'Перерыв':
                comment = 'Break'
                time_game = comment
            else:
                time_game = data.get('liveStatus').get('progress')
                if time_game:
                    time_game = time_game.replace("'", '')
                else:
                    time_game = ''
        elif sport == 'Баскетбол':
            current_score = data.get('liveStatus').get('score')
            sets_score = data.get('liveStatus').get('setScores')
            score = f"{current_score} ({sets_score})"
            comment = data.get('liveStatus').get('stage')
            if comment == 'Перерыв':
                comment = 'Break'
                time_game = comment
            else:
                time_game = data.get('liveStatus').get('progress')
                if time_game:
                    num = re.findall('\d+', time_game)[0]
                    time_game = str(12 - int(num))
                else:
                    time_game = ''
    except Exception:
        print(
            'configure_score_and_time Ошибка при извлечении очков или времени...')
        print(f"Игра: {data['name']}")
    return score.replace("*", '').replace(";", ','), time_game, comment


def get_all_game_content(data, bk_id: str, active_sport: dict) -> dict:  # +
    '''получение всей информации по отдельной игре и запись в БД'''
    sport_id = data.get('league').get('sport').get('id')
    if sport_id not in active_sport:
        return
    else:
        sport_ids = active_sport[sport_id]
    while bd.connect():
        logger.info("ERROR! - No connect BD")
        time.sleep(60)
    cur = bd.cur
    game_name = data.get('name')
    game_id = data.get('id')
    gamer1 = ''
    gamer2 = ''
    gamer1 = game_name.split(' - ')[0]
    gamer2 = game_name.split(' - ')[-1]
    gamer1_id = 0
    gamer2_id = 0
    for g in data.get('competitors'):
        if g.get('name') == gamer1:
            gamer1_id = g.get('id')
        elif g.get('name') == gamer2:
            gamer2_id = g.get('id')
    liga_id = data.get('league').get('id')
    liga_name = data.get('league').get('name')
    sport = data.get('league').get('sport').get('name')
    score, time_game, comment = configure_score_and_time(data)
    created_at = data.get('liveStatus').get('createAt')
    started_at = data.get('kickoff')
    started_at = str(started_at)[:-3]
    started_at = int(started_at)
    period = comment
    # period = data['liveStatus']['stage']
    link = f"https://leon.ru/bets/{data['league']['sport']['url']}/{data['league']['region']['url']}/{data['league']['url']}/{game_id}-{data['url']}"
    try:
        state = data['liveStatus']['fullProgress']['numberOfPeriods']
    except Exception:
        state = ''
    id_game_hash = hashlib.md5(
        (str(game_id) + gamer1 + gamer2 + bk_name).encode('utf-8')).hexdigest()
    gamer_info_1 = hashlib.md5(
        (gamer1 + str(sport_id) + bk_name).encode('utf-8')).hexdigest()
    gamer_info_2 = hashlib.md5(
        (gamer2 + str(sport_id) + bk_name).encode('utf-8')).hexdigest()
    id_liga_hash = hashlib.md5(
        (str(liga_id) + bk_name).encode('utf-8')).hexdigest()
    try:
        liga_info[id_liga_hash] = {
            'liga': liga_name,
            'sport_id': str(sport_ids),
            'name': game_name,
            'bk_id_liga': liga_id,
            'live_is': '1'}
        gamer_info[id_game_hash] = {
            'bk_name': bk_name,
            'id_liga_hash': id_liga_hash,
            'bk_id_gamer1': gamer1_id,
            'bk_id_gamer2': gamer2_id,
            'gamer1': gamer1,
            'gamer2': gamer2,
            'time_game': time_game,
            'score': score,
            'sport_id': str(sport_ids),
            'state': period,
            'link': link,
            'game_id': game_id,
            'gamer_info_1': gamer_info_1,
            'gamer_info_2': gamer_info_2,
            'name': game_name,
            'bk_id': bk_id,
            'liga_info': id_liga_hash,
            'gamer_id_bk': game_id,
            'started_at': started_at,
            'created_at': created_at,
            'update_at': data['lastUpdated'],
            'comment': comment,
        }
    except Exception as e:
        print(f"get_page_content Ошибка преобразования API данных лайв игры - в БД: Игра {data['name']}")
        print(e, type(e))

    sport_name = data.get('league').get('sport').get('name')
    game_live = hashlib.md5(
        (str(game_id) + gamer1 + gamer2 + bk_name).encode('utf-8')).hexdigest()
    for market in data.get('markets'):
        groupName = market.get('name')
        if ('очный счет' in groupName) or ('оличество' in groupName) or ('Кто выиграет' in groupName) or ('Чет/Нечет' in groupName) or ('Чет/нечет' in groupName) or ('то первым' in groupName) or ('по истечении' in groupName) or ('аиболее результативный' in groupName) or ('наберет' in groupName) or ('забьет' in groupName) or ('будет' in groupName) or ('дин из' in groupName) or ('не пропуст' in groupName) or ('хет-трик' in groupName) or ('по угловым' in groupName) or ('в интервале' in groupName) or ('угловых' in groupName) or ('Кто подаст' in groupName) or ('Кто получит' in groupName) or ('карточек' in groupName) or ('Обе ' in groupName) or ('Кто сделает' in groupName) or ('Наиболее' in groupName) or ('с сухим счетом' in groupName) or ('разыгранных очков' in groupName) or ('в каждом периоде' in groupName) or ('в любом из периодов' in groupName) or ('Будет ли' in groupName):
            continue
        for bet in market['runners']:
            # info_koef = {}
            patt_total = re.compile(r'[Тт]отал')
            patt_fora = re.compile(r'[Фф]ора')
            name = bet.get('name')
            param = bet.get('handicap')
            koef = bet.get('priceStr')
            bet_short = name

            if re.search(patt_total, groupName):  # +
                bet_short = bet_short.replace('Меньше ', 'Т_М').replace('Больше ', 'Т_Б').replace(
                    'мен ', 'Т_М').replace('бол ', 'Т_Б').replace('меньше ', 'Т_М').replace('больше ', 'Т_Б')
            elif re.search(patt_fora, groupName):  # +
                bet_short = bet_short.replace(
                    '1 ', 'Ф_К1').replace('2 ', 'Ф_К2')
            elif 'Гандикап' in groupName:  # +
                bet_short = bet_short.replace('1 ', 'К1').replace(
                    '2 ', 'К2').replace('X ', 'Ничья')

            # +
            if ('Победитель' in groupName) or ('Результат не включая ничью' in groupName):
                if '/' in bet_short:
                    bet_short = bet_short.replace('1', 'Поб1').replace(
                        '2', 'Поб2').replace('X', 'Ничья')
                else:
                    bet_short = re.sub(r"^1", 'Поб1', bet_short)
                    bet_short = re.sub(r"^2", 'Поб2', bet_short)
                    bet_short = bet_short.replace('X', 'Ничья')
            elif 'Двойной исход' in groupName:  # +
                bet_short = bet_short.replace(
                    '1X', 'Поб1 или Ничья').replace('12', 'Поб1 или Поб2')
                bet_short = re.sub(r'Х2|2X', 'Ничья или Поб2', bet_short)

            bet_short = bet_short.split()
            bet_short = '_'.join(bet_short)
            if param:
                sh_name = bet_short.replace(param, '')
            else:
                param = 'NULL'
                sh_name = bet_short

            comments = f"{sport_name}. {groupName}. {bet_short}"
            if ('-й' in groupName) or ('-я' in groupName):
                short_name = f"{sport_name}. {groupName}. {sh_name}"
                full_name = f"{groupName}. {bet_short}"
            else:
                short_name = f"{sport_name}. Match {groupName}. {sh_name}"
                full_name = f"Match {groupName}. {bet_short}"
            kof_hash = hashlib.md5(
                (str(game_id) + short_name + str(bk_id) + param).encode('utf-8')).hexdigest()
            period = period.replace('Перерыв', 'Break').replace('Прелайв', 'Prelive').replace('В игре', 'In game').replace(
                'Завершен', 'Completed').replace('Овертайм', 'Overtime').replace('Оверtime', 'Overtime').replace('Овертайм перерыв', 'Overtime Break')

            try:
                dop = {
                    'id': game_id,
                    'groupName': groupName,
                    'name': full_name,
                    'short_name': short_name,
                    'koef': koef,
                    'param': param,
                    'original': bet.get('name'),
                    'link': gamer_info[game_live]['link']
                }
                info_koef[kof_hash] = {
                    'game_live': game_live,
                    "bk_id": str(bk_id),
                    "game_orig": str(game_id),
                    'dop': str(dop),
                    'koef': koef,
                    'name': full_name,
                    'p_name': period,
                    'param': param,
                    'comment': comments,
                    'short_name': short_name,
                    'name_koef_id': hashlib.md5((str(game_id) + str(name) + str(koef) + str(bk_id)).encode('utf-8')).hexdigest(),
                    'name_hash': hashlib.md5((short_name + str(bk_id)).encode('utf-8')).hexdigest(),
                    "created_at": '',
                    "update_at": '',
                }
            except Exception as er:
                print('get_koef error', er, type(er))


def get_one_game_info(game_arr) -> dict:
    '''формирование json для передачи в get_all_game_content
    #  данные формируются в потоке
    '''
    session = requests.Session()
    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:90.0) Gecko/20100101 Firefox/90.0",
        'Content-Type': 'application/json;charset=UTF-8'
    }
    url = game_arr['url']
    proxy_str = game_arr['proxy'].split(':', 1)
    proxy = {
        proxy_str[0]: proxy_str[-1].strip()
    }
    login = game_arr['login']
    password = game_arr['password']
    auth = HTTPProxyAuth(login, password)
    response = session.get(url, headers=headers, proxies=proxy, auth=auth)
    data = response.json()
    return data


def main():
    with requests.Session() as session:
        time1 = datetime.datetime.now()
        with open('logging.log', 'w'):
            pass
        logger.info("Start")
        while bd.connect():
            logger.info("ERROR! - No connect BD")
            print("ERROR! - No connect BD")
            time.sleep(60)
        cur = bd.cur
        headers = {
            'cache-control': 'no-cache',
            'content-type': 'application/json;charset=UTF-8',
            'accept': '*/*',
            'authority': 'leon.ru',
            'referer': 'https://leon.ru/live',
            'user-agent': bd.user_agent_rand(),
        }
        bd.clear_koef(bk_name)
        print('БД очищена...')
        active_sport = bd.active_sport(bk_name)
        bk_id = str(bd.get_bk_id(bk_name))
        DOMAIN = 'https://leon.ru/live'
        main_url = 'https://leon.ru/api-2/betline/events/inplay?ctag=ru-RU&hideClosed=true&flags=reg,mm2,rrc,nodup,urlv2'
        sports_url = 'https://leon.ru/api-2/betline/sports?ctag=ru-RU&flags=urlv2'
        response = get_response(session, sports_url, headers)
        sport_arr = get_info_on_all_sports(response)
        work = True
        while work:
            try:
                t_start = time.time()
                response = get_response(session, main_url, headers)
                gamer_arr_list = get_main_content(response)
                print(f'Всего live-игр {len(gamer_arr_list)}')
                pool_arr = []
                # формирование словаря данных игры для подачи в Pool
                for game in gamer_arr_list:
                    gamer_id = game.get('gamer_id')
                    if not gamer_id:
                        continue
                    game_url = f'https://leon.ru/api-2/betline/event/all?ctag=ru-RU&eventId={gamer_id}&flags=reg,mm2,rrc,nodup,urlv2,smg,outv2'
                    proxies = bd.proxy()
                    n = random.randint(0, len(proxies) - 1)
                    ip = proxies[n][1]
                    port = proxies[n][2]
                    login = proxies[n][3]
                    password = proxies[n][4]
                    proxy = f"http: http://{ip}:{port}"
                    game_arr = {
                        'url': game_url,
                        'proxy': proxy,
                        'login': login,
                        'password': password
                    }
                    pool_arr.append(game_arr)
                with Pool(10) as pool:
                    # получаем json для всех игр
                    result = pool.map(get_one_game_info, pool_arr)
                    now = datetime.datetime.now()
                    print(str(now) + ' - Обработка результатов потока')
                # pool.map возвращает список (словарей) из всех процессов
                for data in result:
                    if len(data) > 0:
                        get_all_game_content(data, bk_id, active_sport)
                    else:
                        print('Пустой результат!')
                bd.add_gamer(gamer_info, bk_id, bk_name)
                bd.add_liga(liga_info, bk_id)
                bd.add_koef_leon(info_koef, bk_id)
                t_end = time.time()
                print(f'Цикл обработки игр {t_end - t_start}')
                gamer_info.clear()
                liga_info.clear()
                info_koef.clear()
            except Exception as er:
                print('*** Main Loop Error ***', er, type(er))
                continue


if __name__ == '__main__':
    while True:
        try:
            main()
            time.sleep(restart_time_pars)
        except UnicodeEncodeError:
            print('Loop -> UnicodeEncodeError')
            print('Sleep 5')
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            logger.info(traceback.format_exc())
            print('Скрипт остановлен')
            bd.cur.close()
            bd.conn.close()
            break
