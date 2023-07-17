#!/usr/bin/python3
# -*- coding: utf-8 -*-
# парсер melbet.ru,  unix format

import bd_scaner as scaner
import os
import re
import sys
import time
import random
import hashlib
import logging
import requests
import datetime
import traceback
from multiprocessing import Pool
appPath = os.path.abspath(os.path.dirname(os.path.join(sys.argv[0])))
inifile = os.path.dirname(appPath) + "/scaner"
sys.path.insert(0, inifile)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('log_melbet.log')
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

PROXY = True  # с использованием прокси
DOMAIN = 'https://melbet.ru/'
LIVE = 'https://melbet.ru/live/'
BK_NAME = 'melbet_ru'
TIMEOUT = 30
RESTART_TIME_PARS = 4
gamer_info = {}
liga_info = {}
info_koef = {}

# подключаемся к БД
while scaner.connect():
    print("ERROR! - No connect BD")
    logger.info("ERROR! - No connect BD")
    time.sleep(60)
cur = scaner.cur

ACTIVE_SPORT = scaner.active_sport(BK_NAME)
BK_ID = str(scaner.get_bk_id(BK_NAME))
USER_AGENT = scaner.user_agent_rand()
if PROXY:
    # получаем список всех доступных прокси один раз
    PROXY_LIST = scaner.get_all_proxy()


def get_response(data: dict):
    '''получение контента веб-страницы'''
    time_start = time.perf_counter()
    response = ''
    proxy = ''
    with requests.Session() as session:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Host": "m.melbet.ru",
            "User-Agent": USER_AGENT,
        }
        url = data['url']
        if PROXY:
            proxy = data['proxy']
            session.proxies = proxy
        try:
            response = session.get(url, headers=headers,
                                   allow_redirects=False, stream=False)
            if response.status_code == 200:
                time_end = time.perf_counter()
                if proxy:
                    if round(time_end - time_start, 2) > 10:
                        print(
                            f'Прокси {proxy} - время обработки {round(time_end - time_start, 2)}')
                        logger.info(
                            f'Прокси {proxy} - время обработки {round(time_end - time_start, 2)}')
            else:
                print(f'* get_response status_code-> {response.status_code}')
        except Exception as e:
            print(f'* Error get_response -> {e}, {type(e)}')
            logger.info(f'* Error get_response -> {traceback.format_exc()}')
        finally:
            return response


def get_main_content(response) -> list:  # +
    '''получение информации о видах спорта и всех играх в лайве'''
    sport_arr = {}
    gamer_arr_list = []
    gamerArr = {}
    try:
        data = response.json()
        for elem in data['Value']:
            sport_id = str(elem['SI'])
            sport_name = elem['SN']
            sport_arr[sport_id] = sport_name
            gamer1 = elem['O1']
            try:
                gamer2 = elem['O2']
            except Exception:
                continue
            gamer_name = f'{gamer1} - {gamer2}'
            gamerArr = {
                'gamer_id': str(elem['I']),
                'name': gamer_name,
                'liga_id': str(elem['LI']),
                'sport_id': sport_id,
            }
            gamer_arr_list.append(gamerArr)
    except Exception as e:
        print(f'Ошибка get_main_content: {e}, {type(e)}')
        logger.info('Ошибка get_main_content')
        logger.info(traceback.format_exc())
    return sport_arr, gamer_arr_list


def get_all_game_response(game_data: dict) -> list:
    '''получение списка основного и дополнительных id для игры(1-й/2-й тайм, Угловые, ЖК, etc) и получение списка response для всех ссылок игры
    '''
    game_id = str(game_data['game_id'])
    full_game_info = []
    all_game_ids = []
    try:
        # получаем все game_id для основного game_id, выбираем только таймы/периоды/сеты, статистику не берем
        # time_start = time.perf_counter()
        response = get_response(game_data)
        if response:
            # добавляем в общий список response основной game_id
            full_game_info.append(response)
            # ищем дополнительные game_id
            data_all = response.json()
            data = data_all.get('Value', '')
            if data:
                dataset = data.get('SG', '')
                if dataset:
                    for el in data['SG']:
                        if (el.get('I') is not None):
                            if (el.get('PN') is not None):
                                sub_id = str(el.get('I'))
                                # sub_id_name = el['PN']
                                all_game_ids.append(sub_id)
                        else:
                            continue
        else:
            print(
                f'get_all_game_response False: данные для {game_id} не получены')
        # для дополнительных game_id получаем данные в список словарей
        if all_game_ids:
            for elem_id in all_game_ids:
                elem_data = {}
                game_url = f'https://m.melbet.ru/LiveFeed/GetGameZip?id={elem_id}&partner=195'
                if PROXY:
                    proxy = game_data['proxy']
                    elem_data = {
                        'url': game_url,
                        'proxy': proxy,
                    }
                else:
                    elem_data = {
                        'url': game_url,
                    }
                response = get_response(elem_data)
                if response:
                    full_game_info.append(response)
        # time_end = time.perf_counter()
        # {round(time_end - time_start, 2)}')
    except Exception as e:
        print(f"Ошибка get_all_game_response: {e}, {type(e)}")
        logger.info("Ошибка get_all_game_response")
        logger.info(traceback.format_exc())
    return full_game_info


def configure_score_and_time(data) -> str:  # +
    """
    Возвращает счет, время матча и комментарий.
    СЧЕТ
    Подгоняем значения под нужный формат.
        Для Тениса и Киберспорта:
        0:0 (0:0, 0:0) 0:0
        # 0:0 это Геймы (0:0 Это Сеты) 0:0 это очки
        Для Баскетбола
        time_game это пройденое время игры
        Для Футбола, Хоккея и Волейбола по аналогии с тенисом
        0:0 (0:0, 0:0)
        # 0:0 это общий счет (0:0 Это счет за тайм)
    :return score: Очки игры в определенном формате
    :return time_game: Время матча, нужны только минуты
    :return comment: "Перерыв", "2-й тайм", "3-й сет"
    """
    sport = data.get('SN')
    score = ""
    comment = ""
    time_game = ''
    try:
        # счет по геймам
        games_score_data = data.get('SC').get('FS')
        try:
            score_gamer1 = games_score_data['S1']
        except KeyError:
            score_gamer1 = '0'  # если FS = {}
        try:
            score_gamer2 = games_score_data['S2']
        except KeyError:
            score_gamer2 = '0'  # если FS = {}
        games_score = f'{score_gamer1}:{score_gamer2}'
        # счет по сетам
        sets_score = ''
        sets_score_list = []
        if data['SC']['PS']:  # если PS != []
            for el in data['SC']['PS']:
                if el['Value']:
                    try:
                        score_g1 = el['Value']['S1']
                    except KeyError:
                        score_g1 = '0'
                    try:
                        score_g2 = el['Value']['S2']
                    except KeyError:
                        score_g2 = '0'
                    set_score = f"{score_g1}:{score_g2}"
                else:
                    set_score = '0:0'
                sets_score_list.append(set_score)
            if len(sets_score_list) > 1:
                for el in sets_score_list[:-1]:
                    s = f'{el}, '
                    sets_score += s
                sets_score = f'({sets_score}{sets_score_list[-1]})'
            else:
                sets_score = f'({sets_score_list[0]})'
        # текущий счет
        current_score = ''
        try:
            current_score = f"{data['SC']['SS']['S1']}:{data['SC']['SS']['S2']}"
        except KeyError:
            current_score = '0:0'
        # время игры
        try:
            time_game = data['SC']['TS']
            time_game = str(round(int(time_game) / 60))
        except KeyError:
            time_game = ''
        # комментарий - состояние игры (1-й тайм, Перерыв)
        try:
            comment = data['SC']['CPS']
        except KeyError:
            try:
                comment = f"{data['SC']['CP']} {data['TN']}"
            except Exception:
                set_num = len(data['SC']['PS'])
                if not set_num:  # если PS == []
                    set_num = '1'
                comment = f"{set_num} {data['TN']}"
        except Exception:
            comment = ''
        if comment == 'Перерыв':
            comment = 'Break'
            time_game = comment
        elif comment == "Игра завершена":
            comment = 'Closed'
            time_game = comment
        # общий счет
        if (sport == 'Теннис') or (sport == 'Киберспорт'):
            score = f'{games_score} {sets_score} {current_score}'
        else:
            score = f'{games_score} {sets_score}'
    except Exception as e:
        print(
            'configure_score_and_time Ошибка при извлечении очков или времени...')
        print(f"Игра: {data.get('O1')} - {data.get('O2')}")
        print(e, type(e))
        logger.info(
            'configure_score_and_time Ошибка при извлечении очков или времени...')
        logger.info(traceback.format_exc())
    return score, time_game, comment


def game_page_content(response, bets_names: dict) -> dict:  # +
    '''получение всей информации по отдельной игре и запись в БД'''
    game_data = response.json()
    data = game_data.get('Value', '')
    if not data:
        return False
    sport_id = str(data.get('SI'))
    bd_sport_id = str(ACTIVE_SPORT[sport_id])
    game_id = str(data.get('I'))
    all_game_ids = ''
    try:
        all_game_ids = data['BIG']
    except Exception:
        pass
    # ищем допольнительные имена ставок
    sub_id_name = ''
    if all_game_ids:
        for el in all_game_ids:
            if str(el['I']) == game_id:
                try:
                    sub_id_name = el['PN']
                except Exception:
                    pass
                try:
                    sub_id_name = f"{sub_id_name} {el['TG']}"
                except Exception:
                    pass
    gamer1 = data.get('O1').replace("'", "")
    gamer2 = data.get('O2').replace("'", "")
    game_name = f"{gamer1} - {gamer2}"
    game_name = game_name.replace("'", "\\'")
    gamer1_slug = f"{data['O1E'].lower().replace(' ', '-').replace('/', '').replace('(', '').replace(')', '').replace('+', '')}"
    gamer2_slug = f"{data['O2E'].lower().replace(' ', '-').replace('/', '').replace('(', '').replace(')', '').replace('+', '')}"
    game_name_slug = f"{gamer1_slug}-{gamer2_slug}"
    try:
        gamer1_id = str(data['O1I'])
    except KeyError:
        gamer1_id = '0'
    try:
        gamer2_id = str(data['O2I'])
    except KeyError:
        gamer2_id = '0'
    liga_id = str(data['LI'])
    liga_name = data.get('L').replace("'", "\\'")
    liga_slug = data.get('LE').replace('.', '').lower().replace(' ', '-')
    sport_slug = data.get('SE').lower().replace(' ', '-')
    score, time_game, comment = configure_score_and_time(data)
    state = comment
    started_at = data.get('S', '')
    link = f'https://melbet.ru/live/{sport_slug}/{liga_id}-{liga_slug}/{game_id}-{game_name_slug}/'
    link = link.replace("'", "\\'")
    id_game_hash = hashlib.md5(
        (game_id + gamer1 + gamer2 + BK_NAME).encode('utf-8')).hexdigest()
    gamer_info_1 = hashlib.md5(
        (gamer1 + str(sport_id) + BK_NAME).encode('utf-8')).hexdigest()
    gamer_info_2 = hashlib.md5(
        (gamer2 + str(sport_id) + BK_NAME).encode('utf-8')).hexdigest()
    id_liga_hash = hashlib.md5(
        (str(liga_id) + BK_NAME).encode('utf-8')).hexdigest()
    try:
        liga_info[id_liga_hash] = {
            "liga": liga_name,
            "sport_id": bd_sport_id,
            "name": game_name,
            "bk_id_liga": liga_id,
            "live_is": "1"
        }
    except Exception as e:
        print(
            f"get_page_content Ошибка формирования liga_info: Игра {data.get('O1')} - {data.get('O2')}")
        print(e, type(e))
        logger.info(
            f"get_page_content Ошибка формирования liga_info: Игра {data.get('O1')} - {data.get('O2')}")
        logger.info(traceback.format_exc())
    try:
        gamer_info[id_game_hash] = {
            "bk_name": BK_NAME,
            "id_liga_hash": str(id_liga_hash),
            "bk_id_gamer1": gamer1_id,
            "bk_id_gamer2": gamer2_id,
            "gamer1": gamer1,
            "gamer2": gamer2,
            "time_game": time_game.replace("'", "\\'"),
            "score": score,
            "sport_id": bd_sport_id,
            "state": state,
            "link": link,
            "game_id": game_id,
            "gamer_info_1": gamer_info_1,
            "gamer_info_2": gamer_info_2,
            "name": game_name,
            "bk_id": BK_ID,
            "liga_info": str(id_liga_hash),
            "gamer_id_bk": game_id,
            "started_at": started_at,
            "created_at": "",
            "update_at": "",
            "comment": comment,
        }
    except Exception as e:
        print(
            f"get_page_content Ошибка формирования gamer_info: Игра {data.get('O1')} - {data.get('O2')}")
        print(e, type(e))
        logger.info(
            f"get_page_content Ошибка формирования gamer_info: Игра {data.get('O1')} - {data.get('O2')}")
        logger.info(traceback.format_exc())

    game_live = hashlib.md5(
        (game_id + gamer1 + gamer2 + BK_NAME).encode('utf-8')).hexdigest()
    markets = data.get('E', '')
    if markets:
        for market in markets:   #
            groupName_id = str(market.get("G"))
            groupName = bets_names.get(groupName_id)['G']
            # фильтр ставок Да/Нет/Какой/Кто и статистики
            if ('Тотал игрока' == groupName) or ('Гол до минуты' == groupName) or ('СуперФора' == groupName) or ('СуперТотал' == groupName) or ('Счет в интервале' in groupName) or ('Следующий гол' in groupName) or ('Какая команда' in groupName) or ('Сухая победа' in groupName) or ('Счет гейма' == groupName) or ('Счет в гейме' == groupName) or ('Ставки в гейме' == groupName) or ('Преимущество в счете' == groupName) or ('Преимущество по геймам' == groupName) or ('Первым выиграет' in groupName) or ('Забитые двухочковые броски' in groupName) or ('Подборы' in groupName) or ('Угловые' in groupName) or ('Фолы' in groupName) or ('Желтые карточки' in groupName) or ('Эйсы' in groupName) or ('Двойные ошибки' in groupName) or ('Поинт' in groupName) or ('Подающий выиграет' in groupName) or ('Промежуточные итоги' in groupName) or ('Тотал розыгрышей в гейме' in groupName) or ('Гонка до' in groupName) or ('Кто сделает брейк' in groupName) or ('Штанги и перекладины' in groupName) or ('количество розыгрышей' in groupName) or ('Брейки' in groupName) or ('Лидер после' in groupName) or ('Цифра в счете' in groupName) or ('Удары в створ' in groupName) or ('Офсайды' in groupName) or ('Удары от ворот' in groupName) or ('Вброс аутов' in groupName) or ('Будет ли' in groupName) or ('Ошибки на' in groupName) or ('Блоки' in groupName):
                continue
            koef_name = bets_names.get(groupName_id)[
                'B'][str(market['T'])]['N']
            bet_short = koef_name
            koef = str(market.get('C'))
            param = str(market.get('P'))
            # param type float  2.0  114129.103118
            if param != 'None':
                param = re.sub(r'[.]0$', '', param)
            else:
                param = 'NULL'
            paramDB = param
            if paramDB != 'NULL':
                pattern = re.compile("\d+\.[\d+]{3,}")
                # убираем param вида 79091.08409, оставляем 125.05
                if re.findall(pattern, paramDB):
                    paramDB = 'NULL'
            try:
                if groupName_id == '1144':  # Точная разность очков
                    if param != 'NULL':
                        p1 = int(float(param))
                        p2 = p1 + 4
                        bet_short = bet_short.replace(
                            "()", f'{p1}', 1).replace("()", f'{p2}', 2)
                elif groupName_id == '3319' or groupName_id == '3313':
                    # 3319   Точное количество очков
                    # 3313   Точное количество шайб
                    if '.' in param:
                        #  Тотал () - ()   91.1  81.09  101.11  131.14
                        p1, p2 = param.split('.')
                        p2 = p2 + '0'
                        if re.findall(r'^0', p2):
                            p2 = re.sub(r'^0', '', p2)
                        if re.findall(r'^9', p1):
                            p2 = p2 + '0'
                        bet_short = bet_short.replace(
                            "()", f'{p1}', 1).replace("()", f'{p2}', 2)
                    else:
                        #  151   Тотал () и более
                        bet_short = bet_short.replace("()", f'{param}')
                elif groupName_id == '952':
                    # 952   Точный счет по сетам   Cчет ()-() по сетам
                    if '.' in param:
                        #  Cчет ()-() по сетам   300.01   100.02
                        p1, p2 = param.split('.')
                        p2 = p2 + '0'
                        if re.findall(r'^0', p2):
                            p2 = re.sub(r'^0', '', p2)
                        if re.findall(r'0$', p1):
                            p1 = re.sub(r'0$', '', p1)
                            if re.findall(r'0$', p1):
                                p1 = re.sub(r'0$', '', p1)
                        bet_short = bet_short.replace(
                            "()", f'{p1}', 1).replace("()", f'{p2}', 2)
                    else:
                        #  151   Тотал () и более
                        bet_short = bet_short.replace("()", f'{param}')
                elif groupName_id == '6757':  # СуперФора
                    p1 = int(float(param))
                    n1, n2 = bet_short.split(':')
                    n2 = f'({p1 - 0.5})'
                    # n2 = f'{p1 - 0.5}'
                    bet_short = f'{n1} {n2}'
                elif groupName_id == '6755':  # СуперТотал
                    p1 = int(float(param))
                    n1, n2 = bet_short.split(':')
                    if re.findall(r'Б$', n2):
                        bet_short = f'{n1} {p1 + 1.5} Б'
                    elif re.findall(r'М$', n2):
                        bet_short = f'{n1} ({p1 - 0.5}) М'
                elif (groupName_id == '136') or (groupName_id == '2878') or (groupName_id == '2876') or (groupName_id == '9936') or (groupName_id == '2750') or (groupName_id == '2752'):
                    # 136   Точный счет
                    # 9936   Победа в интервале (3 исхода)
                    # 2876/2878   Команда 1/2 забьет N голов
                    # 2750   Исход на оставшееся время
                    # 2752   Двойной шанс на оставшееся время
                    if param != 'NULL':
                        if '.00' in param:
                            p1, p2 = param.split('.00')
                        elif '.0' in param:
                            p1, p2 = param.split('.0')
                            if len(p1) == len(p2):
                                p2 = p2 + '0'
                        else:
                            p1 = param
                            p2 = 0
                    else:
                        p1, p2 = 0, 0
                    bet_short = bet_short.replace("()", "{}").format(p1, p2)
                elif (groupName_id == '7961') or ('мультигол' in groupName) or (groupName_id == '28') or (groupName_id == '347') or (groupName_id == '7833') or (groupName_id == '9126') or (groupName_id == '9936'):
                    # 7961   Мультигол   Мультигол ()-()/Команда 1, мультигол ()-()
                    # 347   Победа в интервале
                    # 7833 (2 исхода)  9126 (4 исхода)  9936 (3 исхода)
                    # 28   Тотал промежуток
                    if '.' in param:
                        p1, p2 = param.split('.')
                        if re.findall(r'^0', p2):
                            p2 = re.sub(r'^0', '', p2)
                            if re.findall(r'^0', p2):
                                p2 = re.sub(r'^0', '', p2)
                        bet_short = bet_short.replace(
                            "()", "{}").format(p1, p2)
                    else:
                        bet_short = bet_short.replace("()", f"{param}")
                elif ('Исход интервала' in groupName) or (groupName_id == '2833') or (groupName_id == '2835') or (groupName_id == '2837') or (groupName_id == '9396') or (groupName_id == '887') or (groupName_id == '10036'):
                    # 2833 Двойной исход (5 м)
                    # 9396 Двойной исход (30 м)
                    # 887   Гол в интервале - Да/Нет
                    # 10036   Команды, время гола
                    # П1 с ():00 по ():59 мин / 12 с ():00 по конец матча
                    if '.' in param:
                        p1, p2 = param.split('.0')
                        if len(p2) == 1:
                            p2 = p2 + '0'
                        bet_short = bet_short.replace(
                            "()", "{}").format(p1, p2)
                    else:
                        bet_short = bet_short.replace("()", f"{param}")
                elif (groupName_id == '2884') or (groupName_id == '2886') or (groupName_id == '96'):
                    # 96   Гол до минуты
                    # 2884/2886   Команда 1/2 забьет гол N с минуты по минуту
                    p1, p2 = param.split('.00')
                    bet_short = bet_short.replace("()", "{}").format(p2, p1)
                elif groupName_id == '8865':
                    # Счет в интервале ()-():()-()
                    p1, p2 = param.split('.')
                    if len(p1) == 5:
                        p1_1 = p1[:2]
                        p1_2 = p1[2:]
                        p1_2 = re.sub(r'^0', '', p1_2)
                    elif len(p1) == 6:
                        p1_1 = p1[:3]
                        p1_2 = p1[3:]
                    if len(p2) == 5:
                        p2 = p2 + '0'
                    p2_1 = p2[:3]
                    p2_2 = p2[3:]
                    p2_1 = re.sub(r'^0', '', p2_1)
                    p2_2 = re.sub(r'^0', '', p2_2)
                    bet_short = bet_short.replace(
                        "()", "{}").format(p1_1, p1_2, p2_1, p2_2)
                elif (groupName_id == '147') or (groupName_id == '10439'):
                    # 147   Счет после сетов
                    # 10439   Счет после партий   счет ()-() после () сетов
                    if '.' in param:
                        p1, p2 = param.split('.')
                        bet_short = bet_short.replace(
                            "()", "{}").format(p1[-1], p2[-1], p1[0])
                    else:
                        bet_short = bet_short.replace("()", "{}").format(
                            param[0], param[1], param[-1])
                elif (groupName_id == '9380') or (groupName_id == '9381') or (groupName_id == '1128') or (groupName_id == '2839') or (groupName_id == '2841') or (groupName_id == '2843') or (groupName_id == '9397'):

                    p1, p2 = param.split('.')
                    p1_1 = f'({int(p1) / 100})'
                    p2_1 = p2[:2]
                    p2_2 = p2[2:]
                    bet_short = bet_short.replace(
                        "()", "{}").format(p1_1, p2_1, p2_2)
                elif groupName_id == '60' or groupName_id == '20':
                    # 60   Гонка до   Гонка до () голов победит Команда 1
                    # 20   Следующий гол
                    bet_short = bet_short.replace("()", f"{param}")
                elif groupName_id == '110':  # Количество сетов
                    # Кол-во сетов ()   300.003
                    p1 = param[0]
                    bet_short = bet_short.replace("()", f"{p1}")
                elif groupName_id == '864':  # Победа с преимуществом
                    if '.00' in param:
                        p1, p2 = param.split('.00')
                        bet_short = bet_short.replace(
                            "()", "{}").format(p2, p1)
                    else:
                        bet_short = bet_short.replace("()", "{}").format(param)

                else:  # остальные - с параметром в ()
                    if param == 'NULL':
                        bet_short = bet_short.replace("()", "(0)")
                    else:
                        bet_short = bet_short.replace("()", f"({param})")

                bet_short = re.sub(
                    'Команда 1|Игрок 1|Первый наберет|Первый забьет', 'К1', bet_short)
                bet_short = re.sub(
                    "Команда 2|Игрок 2|Второй наберет|Второй забьет", "К2", bet_short)
                bet_short = re.sub(r' - НЕТ$', '', bet_short)
                bet_short = re.sub(r' - Нет$', '', bet_short)
                bet_short = re.sub(r': нет$', '', bet_short)
                bet_short = re.sub(r' - ДА$', '', bet_short)
                bet_short = re.sub(r' - Да$', '', bet_short)
                bet_short = re.sub(r': да$', '', bet_short)
                bet_short = re.sub('<', 'М', bet_short)
                bet_short = re.sub('>', 'Б', bet_short)
            except Exception as e:
                print(
                    f"get_page_content Ошибка расшифровки ставок: {groupName} / {koef_name} / param = {param}")
                print(e, type(e))
                logger.info(
                    f"get_page_content Ошибка расшифровки ставок: {groupName} / {koef_name} / param = {param}")
                logger.info(traceback.format_exc())

            original = bet_short
            bet_short = bet_short.split()
            bet_short = '_'.join(bet_short)
            sport_name = data.get('SN')
            koef_name_ = koef_name
            koef_name_ = re.sub(r' - НЕТ$', '', koef_name_)
            koef_name_ = re.sub(r' - Нет$', '', koef_name_)
            koef_name_ = re.sub(r': нет$', '', koef_name_)
            koef_name_ = re.sub(r' - ДА$', '', koef_name_)
            koef_name_ = re.sub(r' - Да$', '', koef_name_)
            koef_name_ = re.sub(r': да$', '', koef_name_)
            koef_name_ = re.sub('<', 'М', koef_name_)
            koef_name_ = re.sub('>', 'Б', koef_name_)

            if (groupName == '1X2') or (groupName == '1x2') or (groupName == 'Фора') or (groupName == 'Тотал') or (groupName == 'Точный счёт матча') or (groupName == 'Двойной шанс') or (groupName == 'Точный счёт') or (groupName == 'Европейский гандикап') or (groupName == 'Победа в матче'):
                if sub_id_name:
                    short_name = f"{sport_name}. {sub_id_name} {groupName} {koef_name_}"
                    name = f"{sub_id_name} {groupName} {koef_name_}"
                else:
                    short_name = f"{sport_name}. Match {koef_name_}"
                    name = f"Match {koef_name_}"
            else:
                if sub_id_name:
                    short_name = f"{sport_name}. {sub_id_name} {groupName} {koef_name_}"
                    name = f"{sub_id_name} {groupName} {koef_name_}"
                else:
                    short_name = f"{sport_name}. {groupName} {koef_name_}"
                    name = f"{groupName} {koef_name_}"

            kof_hash = hashlib.md5(
                (game_id + short_name + BK_ID + paramDB).encode('utf-8')).hexdigest()
            name_hash = hashlib.md5(
                (short_name + BK_ID).encode('utf-8')).hexdigest()
            comment = short_name
            try:
                dop = {
                    'id': game_id,
                    'groupName': groupName,
                    'name': name,
                    'short_name': short_name,
                    'koef': koef,
                    'param': paramDB,
                    'original': original,
                    'link': link
                }
            except Exception:
                print(
                    f"get_page_content Ошибка формирования dop: {groupName} / {koef_name}")
                print(traceback.format_exc())
                logger.info(
                    f"get_page_content Ошибка формирования dop: {groupName} / {koef_name}")
                logger.info(traceback.format_exc())
            name_koef_id = hashlib.md5(
                (game_id + str(name) + str(koef) + BK_ID).encode('utf-8')).hexdigest()
            try:
                info_koef[kof_hash] = {
                    "game_live": game_live,
                    "bk_id": BK_ID,
                    "game_orig": game_id,
                    "name": name,
                    "short_name": short_name,
                    "koef": koef,
                    "id": game_id,
                    "name_hash": name_hash,
                    "comment": comment,
                    'p_name': state,
                    "param": paramDB,
                    "dop": str(dop),
                    "name_koef_id": name_koef_id,
                    "groupName": groupName,
                    "created_at": "",
                    "update_at": "",
                }
            except Exception:
                print(
                    f"get_page_content Ошибка формирования info_koef: {groupName} / {koef_name}")
                print(traceback.format_exc())
                logger.info(
                    f"get_page_content Ошибка формирования info_koef: {groupName} / {koef_name}")
                logger.info(traceback.format_exc())


def get_bets_names() -> dict:
    '''получение словаря с расшифровкой ставок'''
    data = {}
    proxy_flag = True  # получение словаря через прокси
    try:
        with requests.Session() as session:
            url = 'https://m.melbet.ru/genfiles/cms/betstemplates/betsNames_ru.js'
            if proxy_flag:
                proxy = {
                    'http': 'http://8abcEFES:X8abcEFES@194.23.238.50:60940',
                    'https': 'http://8abcEFES:X8abcEFES@194.23.238.50:60940'
                }
                session.proxies = proxy
            response = session.get(url)
            response = response.text
            data = response.replace('var betsModel = ', '')
            data = re.sub(r';$', '', data)
            data = eval(data)
    except Exception:
        print(f'get_bets_names -> {traceback.format_exc()}')
        logger.info(f"get_bets_names: {traceback.format_exc()}")
    return data


def get_random_proxy(proxy_list: list) -> dict:
    '''рандомный прокси из списка прокси'''
    n = random.randint(0, len(proxy_list) - 1)
    ip = proxy_list[n][1]
    port = proxy_list[n][2]
    login = proxy_list[n][3]
    password = proxy_list[n][4]
    http = f'http://{login}:{password}@{ip}:{port}'
    proxy = {
        'http': http,
        'https': http
    }
    return proxy


def main():
    # time1 = datetime.datetime.now()
    with open('log_melbet.log', 'w'):
        pass
    logger.info("Start melbet_ru")
    scaner.clear_koef(BK_NAME)
    print('БД очищена...')
    print(f'Использование прокси {PROXY}')
    # получение документа с расшифровкой ставок
    logger.info("Получение документа с расшифровкой ставок")
    success = False
    for _ in range(5):
        try:
            bets_names = get_bets_names()
            if bets_names:
                print('Получены bets_names с сайта')
                logger.info("Получены bets_names с сайта")
                success = True
                break
        except Exception:
            print('НЕ ПОЛУЧЕНЫ bets_names !!!')
            logger.info("НЕ ПОЛУЧЕНЫ bets_names !!!")
            time.sleep(1)
            continue
    if not success:
        logger.info(' Нужно проверить сайт с расшифровкой ставок! ')
        time.sleep(20)
        return
    main_url = 'https://m.melbet.ru/LiveFeed/Get1x2_VZip?count=1000&gr=241&antisports=198&mode=4&cyberFlag=4&country=1&partner=195&getEmpty=true&mobi=true'
    work = True
    while work:
        try:
            print('-----------------------')
            main_dict = {}
            t_start = time.perf_counter()
            if PROXY:
                # рандомный прокси из фиксированного списка
                main_proxy = get_random_proxy(PROXY_LIST)
                main_dict = {
                    'url': main_url,
                    'proxy': main_proxy,
                }
            else:
                main_dict = {
                    'url': main_url,
                }
            response = get_response(main_dict)
            if not response:
                print(
                    '* Not response, нужно проверить работоспособность сайта или прокси!')
                work = False
                break
            sport_arr, gamer_arr_list = get_main_content(response)
            print(f'Сейчас в live игр {len(gamer_arr_list)}')
            pool_game_ids = []
            for game in gamer_arr_list:
                game_data = {}
                # фильтр нужных видов спорта
                if game['sport_id'] not in ACTIVE_SPORT:
                    continue
                game_id = game.get('gamer_id', '')
                if not game_id:
                    continue
                # сначала парсим основной id игры, чтобы получить все доп id
                game_long_url = f'https://m.melbet.ru/LiveFeed/GetGameZip?id={game_id}&lng=ru&cfview=0&isSubGames=true&GroupEvents=true&countevents=300&partner=195&grMode=2'
                if PROXY:
                    # рандомный прокси из списка
                    one_game_proxy = get_random_proxy(PROXY_LIST)
                    game_data = {
                        'game_id': game_id,
                        'url': game_long_url,
                        'proxy': one_game_proxy,
                    }
                else:
                    game_data = {
                        'game_id': game_id,
                        'url': game_long_url,
                    }
                pool_game_ids.append(game_data)
            print(f'Сформирован список для Pool {len(pool_game_ids)}')
            # собираем все id для одной игры(матч+периоды/таймы/сеты...)
            # здесь же проходим по всем ссылкам для игры
            with Pool(20) as pool:
                try:
                    t_pool_start = time.perf_counter()
                    full_response_list = pool.map(
                        get_all_game_response,
                        pool_game_ids
                    )
                    t_pool_end = time.perf_counter()
                    print(
                        f'Время обработки Pool {round(t_pool_end - t_pool_start, 3)}')
                    now = datetime.datetime.now()
                    print(str(now) + ' - Обработка результатов потока')
                except Exception:
                    print(f"Ошибка Pool: {traceback.format_exc()}")
                    logger.info(f"Ошибка Pool: {traceback.format_exc()}")
                    pass
            try:
                t1 = time.perf_counter()
                counter = 0
                # full_response_list - список списков response
                for response_list in full_response_list:
                    for response in response_list:
                        game_page_content(response, bets_names)
                        counter += 1
                t2 = time.perf_counter()
                print(f'Обработка результатов потока {round(t2 - t1, 3)}')
                print(f'Обработано ссылок {counter}')
            except Exception:
                print("Ошибка обработки game_page_content: ")
                print(traceback.format_exc())
                logger.info("Ошибка обработки game_page_content: ")
                logger.info(traceback.format_exc())
                pass
            # t_db = time.perf_counter()
            scaner.add_liga(liga_info, BK_ID)  # +
            try:
                scaner.add_gamer(gamer_info, BK_ID, BK_NAME)
            except Exception:
                print('*** Ошибка записи add_gamer: ')
                print(traceback.format_exc())
                logger.info('*** Ошибка записи add_gamer: ')
                logger.info(traceback.format_exc())
                pass
            try:
                scaner.add_koef_leon(info_koef, BK_ID)
            except Exception:
                print('*** Ошибка записи add_koef_leon: ')
                print(traceback.format_exc())
                logger.info('*** Ошибка записи add_koef_leon: ')
                logger.info(traceback.format_exc())
                pass
            t_end = time.perf_counter()
            # print(f'Запись в БД {round(t_end - t_db, 3)}')
            print(f'Цикл обработки игр {round(t_end - t_start, 3)}')
        except KeyboardInterrupt:
            print('Main - Скрипт остановлен')
            scaner.cur.close()
            scaner.conn.close()
            break
        except Exception:
            print("*** Ошибка в main: ")
            print(traceback.format_exc())
            logger.info("*** Ошибка в main: ")
            logger.info(traceback.format_exc())
            pass
        finally:
            gamer_info.clear()
            liga_info.clear()
            info_koef.clear()


if __name__ == '__main__':
    while True:
        try:
            main()
            time.sleep(RESTART_TIME_PARS)
        except ConnectionResetError:
            print('Loop - ConnectionResetError, sleep 10 sec')
            time.sleep(10)
            continue
        except UnicodeEncodeError:
            print('Loop -> UnicodeEncodeError')
            print('Sleep 5')
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            logger.info('Loop - Скрипт остановлен')
            scaner.cur.close()
            scaner.conn.close()
            break
        except Exception:
            logger.info(traceback.format_exc())
            raise
            time.sleep(RESTART_TIME_PARS)
            continue
