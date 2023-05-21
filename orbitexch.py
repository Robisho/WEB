# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import bd_scaner as bd
import asyncio
import hashlib
import json
import os
import re
import sys
from time import time, sleep

import js2py as js2py
import requests
import websockets
from loguru import logger

sys.path.insert(0, "../bd")

logger.remove()
# логи для локальной консоли
logger.add(sys.stderr, format="{message}", level="DEBUG")


def get_token():
    f = js2py.eval_js(
        "function a(e) {return e ? (e ^ 16 * Math.random() >> e / 4).toString(16) : ([1e16] + 1e16).replace(/[01]/g, a)}")
    return f(1)


async def websocket_requests(event_id, market_id):  # +
    uri = "wss://orbitexch.com/customer/ws/market-prices/968/m03argpu/websocket"
    async with websockets.connect(uri) as websocket:
        name = json.dumps(
            ["{\"eventId\":\"%s\",\"marketId\":\"%s\",\"applicationType\":\"WEB\"}" % (event_id, market_id)])
        # print(name)
        greeting = await websocket.recv()
        # print(f"<<< {greeting}")
        await websocket.send(name)
        # print(f">>> {name}")
        greeting = await websocket.recv()
        # print(f"<<< {greeting}")
        # print(greeting)
        return greeting


def check_site_status() -> bool:
    '''проверка доступности биржи, может быть на техобслуживании'''
    res = requests.get('https://orbitexch.com/customer/inplay/highlights/1')
    html_code = res.text
    title = html_code[html_code.find(
        '<title>') + 7: html_code.find('</title>')]
    flag = True
    if title == 'Site under maintenance':
        # print('Site under maintenance')
        flag = False
    return flag


def get_active_live_games(headers) -> list:  # +
    """Получим все активные live игры со страницы
    https://orbitexch.com/customer/inplay/highlights/1"""
    logger.debug('Получаем активные live игры...')
    params = {
        'page': 0,
        'size': 60
    }
    data = {
        'viewBy': "TIME",
        'from': round(time()) * 1000
    }
    cookies = {
        'CSRF-TOKEN': token,
    }
    url = 'https://orbitexch.com/customer/api/inplay/now'
    all_data = []
    while True:
        with session.post(url, headers=headers, params=params, data=json.dumps(data), cookies=cookies) as req:
            # print('req.json', req.json())
            all_data.extend(req.json()['marketCatalogueList']['content'])
        if req.json()['marketCatalogueList']['totalElements'] > len(all_data):
            params['page'] += 1
        else:
            break
    # получим очки...
    update_url = 'https://orbitexch.com/customer/api/event-updates'
    payload_data = [data['event']['id'] for data in all_data]
    sports_data = {}
    for data in all_data:
        sports_data[data['eventType']['id']] = data['eventType']['name']
    with session.post(update_url, headers=headers, params=params, data=json.dumps(payload_data), cookies=cookies) as req:
        for update in req.json():
            for data in all_data:
                if data['event']['id'] == update['eventId']:
                    data['update'] = update
                    # print('data[update] -> ', data['update'])  # +
    print('Всего лайв игр', len(all_data))  # +
    return all_data


def get_live(live) -> dict:  # +
    """
    формируются словари gamer_live, liga_info и gamer_info
    пример данных, которые надо отправить на запись:
    :gamer_info:
    {'7c0ed7e45e12bc32b6d121e6466a3627': {
        'bk_id_gamer1': 13968899,
        'bk_id_gamer2': 13621574,
        'gamer1': 'Club Tijuana (W)',
        'gamer2': 'Cruz Azul (W)',
        'gamer_info_1': '2f354948dc2924a2899f664ed1f91656',
        'gamer_info_2': '59c90d421b7d050f1b8dc190f30ed31c',
        'id_liga_hash': 'e9f7935927e721c36880b34d794627c2',
        'link': 'https://orbitexch.com/customer/sport/event/31071686', 'sport_id': 1,
        'game_id': '31071686',
        'score': '',
        'started_at': 1637031792000,
        'state': '',
        'time_game': 'None',
        'comment': ''
        }
    }
    :param live: API данные
    :return:
    """
    logger.debug('Извлекаем live...')
    gamer_info, gamer_live, liga_info = {}, {}, {}
    gamer_name = live['event']['name']
    try:
        competitor1, competitor2 = gamer_name.split(' v ')
    except Exception:
        competitor1, competitor2 = gamer_name.split(' @ ')
    score, match_time, comment = configure_score_and_time(live)
    liga_id = live['competition']['id']
    liga_name = live['competition']['name']
    id_game_hash = hashlib.md5(
        (str(live['event']['id']) + bk_name).encode('utf-8')).hexdigest()
    gamer_info_1 = hashlib.md5(
        (str(competitor1) + bk_name).encode()).hexdigest()
    gamer_info_2 = hashlib.md5(
        (str(competitor2) + bk_name).encode()).hexdigest()
    id_liga_hash = hashlib.md5(
        (str(live['competition']['id']) + bk_name).encode()).hexdigest()
    try:
        gamer_live[id_game_hash] = {
            'gamer_id_bk': live['event']['id'],
            'liga_info': id_liga_hash,
            'bk_id': bk_id,
            'name': gamer_name,
            'gamer_info_1': gamer_info_1,
            'gamer_info_2': gamer_info_2,
            'time_game': match_time,
            'score': score,
            'comment': comment,
            'link': f"https://orbitexch.com/customer/sport/event/{live['event']['id']}",
            'started_at': live['marketStartTime'],
            'created_at': '',
            'update_at': '',
        }
        liga_info[id_liga_hash] = {
            'liga': liga_name,
            'sport_id': live['eventType']['id'],
            'bk_id_liga': liga_id,
            'live_is': '1'}

        # period = configure_period(live)
        period = ""
        gamer_info[id_game_hash] = {
            'bk_name': bk_name,
            'id_liga_hash': id_liga_hash,
            'bk_id_gamer1': live['runners'][0]['selectionId'],
            'bk_id_gamer2': live['runners'][1]['selectionId'],
            'gamer1': competitor1,
            'gamer2': competitor2,
            'time_game': match_time,
            'score': score,
            'started_at': live['marketStartTime'],
            'sport_id': live['eventType']['id'],
            'state': period,
            'link': f"https://orbitexch.com/customer/sport/event/{live['event']['id']}",
            'game_id': live['event']['id'],
            'gamer_info_1': gamer_info_1,
            'gamer_info_2': gamer_info_2,
            'name': gamer_name,
            'bk_id': bk_id,
            'liga_info': id_liga_hash,
            'gamer_id_bk': live['event']['id'],
            'created_at': '',
            'update_at': '',
            'comment': comment
        }
        # print(gamer_info)
        # print(gamer_live)
        # print(liga_info)
        bd.add_gamer(gamer_info, bk_id, bk_name)
        bd.add_liga(liga_info, bk_id)
    except Exception as e:
        logger.opt(exception=True).critical(
            "get_live Ошибка преобразования API данных лайв игры - в БД: {}", e)
        logger.error('API данные лайв игры:\n' + str(live))
        print(e, type(e))


def configure_score_and_time(live):  # +
    """
    Возвращает счет, время матча и комментарий.
    СЧЕТ
    Подгоняем значения под нужный формат.
        Для Тениса:
        0:0 (0:0, 0:0) 0:0
        # 0:0 это Геймы (0:0 Это Сеты) 0:0 это очки
        Для Футбола и Хоккея и Баскетбола и Волейбола по аналогии с тенисом
        0:0 (0:0, 0:0)
        # 0:0 это общий счет (0:0 Это счет за тайм)
    :param live:
    :return score: Очки игры в определенном формате
    :return match_time: Время матча, нужны только минуты
    :return comment: если в футболе есть дополнительное время, или в теннисе кто подает
    """
    score = ""
    comment = ""
    match_time = 'None'
    if live.get('update') is None:
        return score, match_time, comment
    home = live['update']['score']['home']
    away = live['update']['score']['away']
    sport_id = live['eventType']['id']
    try:
        if sport_id == '2':  # 2 - Теннис
            if (home.get('games') is not None) and (away.get('games') is not None):
                games_score = f"{home.get('games')}:{away.get('games')}"
            else:
                games_score = '0:0'
            sets_score = ''
            if (home.get('sets') is not None) and (away.get('sets') is not None):
                sets_score = f"{home.get('sets')}:{away.get('sets')}"
            else:
                sets_score = '0:0'
            current_score = ''
            if (home.get('score') is not None) and (away.get('score') is not None):
                current_score = f"{home.get('score')}:{away.get('score')}"
            else:
                current_score = '0:0'
            score = f'{games_score} ({sets_score}) {current_score}'
            match_time = str(live['update'].get('timeElapsed'))

        # 1 Футбол, NULL наст. тенис, 7524 хоккей, 7522 баскетбол, 998917
        # волейбол
        elif sport_id in ['1', '7524', '7522', '998917']:
            current_score = ''
            if home['score'] and away['score']:
                current_score = f"{home.get('score')}:{away.get('score')}"
            else:
                current_score = '0:0'
            sets_score = ''
            # if live['update'].get('inPlayMatchStatus') == 'SecondHalfKickOff':  второй тайм
            # 'KickOff' - первый тайм, "FirstHalfEnd" - перерыв
            # "elapsedAddedTime" - добавленное время
            # 'elapsedRegularTime' - основное время
            # 'timeElapsed' - общее время
            if home['halfTimeScore'] and away['halfTimeScore']:
                sets_score = f"{home.get('halfTimeScore')}:{away.get('halfTimeScore')}"
            else:
                sets_score = "0:0"
            score = f"{current_score} ({sets_score})"
            match_time = str(live['update'].get('timeElapsed'))
    except Exception:
        logger.error('configure_score_and_time Ошибка при извлечении очков или времени...\n'
                     'API данные лайв игры:\n' + str(live['event']['name']))
    return score, match_time, comment


# +
def set_odd(live, odd, name, period, market, outcomes, competitor1, competitor2, index) -> dict:
    '''формирование словаря odds и запись его в БД'''
    odds = {}
    comment = ''  # comment везде отсутствует, оставляем таким
    name_short = f"{name}".replace(
        competitor1, 'К1').replace(competitor2, 'К2')
    key = hashlib.md5((str(market['marketId']) + str(outcomes['rc'][index]['id']) + str(odd['index']) + name + str(
        live['event']['id'])).encode('utf-8')).hexdigest()
    dop = {
        "market_id": market['marketId'],
        "name": name,
        "odds_id": outcomes['rc'][index]['id'],
        "odd_index": odd['index']
    }
    # info_koef
    odds[key] = {
        'game_live': key,
        "bk_id": bk_id,
        'dop': str(dop),
        'game_orig': live['event']['name'],
        'id': live['event']['id'],
        'koef': odd['odds'],
        'name': name,
        'p_name': period,
        'param': outcomes['rc'][index]['hc'],
        'comment': comment,
        'short_name': name_short,
        'name_hash': hashlib.md5((str(name_short) + bk_name).encode('utf-8')).hexdigest(),
        "created_at": '',
        "update_at": '',
    }
    bd.add_koef_ggbet(odds, bk_id)


def get_odds(live, headers):  # +
    """
    Записываем коэффициенты в БД
    пример словаря, передаваемого для записи в БД:
    [{'ffe44d4beb01643cd8361eee6b2e72ad': {                  - hash от коэффициента, должен быть уникальным для каждого коэффициента
        'dop': '2-й сет|Победа 2~%P|2657|8.0|8:11',          - информация, чтобы потом найти коэффициент на странице
        'game_live': '1ecf01685549461aaeb68390488f4057',     - ключ от словаря, который 'ffe44d4beb01643cd8361eee6b2e72ad'
        'game_orig': 29122351,                               - id игры на сайте
        'koef': '8.0',                                       - коэффициент
        'name': 'Победа 2 %P',                               - Название для коэффициента. С именами игроков и параметрами. Примеры ниже
        'name_hash': '01fea1d99c0e77207a68162c2db08542',     - hash от short_name
        'p_name': '2-й сет',                                 - период, на который идет ставка, или Match если на ставка на всю игру
        'param': '8:11',                                     - параметр ставки, hcp или total
        'short_name': '2657'                                 - короткое имя. p_name + name. Заменяем игроков на К1 и К2. Убираем параметры
    },}]
    :param live: API данные
    :return:
    """
    logger.debug('Извлекаем коэффициенты...')

    url = f"https://orbitexch.com/customer/api/multi-market/tabs/{live['event']['id']}"
    with session.get(url, headers=headers) as req:
        group_markets = req.json()

    print('Игра ', live['event']['name'])
    try:
        competitor1, competitor2 = live['event']['name'].split(' v ')
    except Exception:
        competitor1, competitor2 = live['event']['name'].split(' @ ')
    try:
        for group in group_markets:
            period = group['tabName']
            for market in group['marketCatalogues']:
                outcomes = json.loads(asyncio.run(websocket_requests(
                    market['event']['id'], market['marketId']))[1:])[0]
                outcomes = json.loads(outcomes)
                if outcomes['marketDefinition']['status'] == 'SUSPENDED':
                    # маркет закрыт, ставки не принимаются
                    # print('Market SUSPENDED')
                    continue

                market_name = market['marketName']
                market_type = market['description']['marketType']

                if market_type == 'BOTH_TEAMS_TO_SCORE':
                    for index, yn in [(0, 'Yes'), (1, 'No')]:
                        for odd in outcomes['rc'][index]['bdatb']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Back (Bet For) - ' + yn
                            name = f"{market_name} - {period} - Back (Bet For) - {yn}"
                            set_odd(
                                live,
                                odd,
                                name,
                                period,
                                market,
                                outcomes,
                                competitor1,
                                competitor2,
                                index
                            )

                        for odd in outcomes['rc'][index]['bdatl']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Lay (Bet Against) - ' + yn
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2,
                                index
                            )

                elif 'OVER_UNDER' in market_type:
                    param = int(market_type.split('_')[-1]) / 10
                    for index, yn in [(0, f'Under {param} Goals'), (1, f'Over {param} Goals')]:
                        for odd in outcomes['rc'][index]['bdatb']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Back (Bet For) - ' + yn
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2,
                                index
                            )

                        for odd in outcomes['rc'][index]['bdatl']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Lay (Bet Against) - ' + yn
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2,
                                index
                            )

                elif market_type == 'MATCH_ODDS':
                    for index, yn in [(0, live['runners'][0]['runnerName']), (1, live['runners'][1]['runnerName']), (2, live['runners'][2]['runnerName'])]:
                        for odd in outcomes['rc'][index]['bdatb']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Back (Bet For) - ' + yn
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2, index
                            )

                        for odd in outcomes['rc'][index]['bdatl']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Lay (Bet Against) - ' + yn
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2, index
                            )

                elif market_type == 'DOUBLE_CHANCE':
                    for index, yn in [(0, 'Home or Draw'), (1, 'Draw or Away'), (2, 'Home or Away')]:
                        for odd in outcomes['rc'][index]['bdatb']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Back (Bet For) - ' + yn
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2, index
                            )

                        for odd in outcomes['rc'][index]['bdatl']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Lay (Bet Against) - ' + yn
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2, index
                            )

                elif market_type in ['ASIAN_HANDICAP', 'DRAW_NO_BET']:
                    for index, yn in [(0, live['runners'][0]['runnerName']), (1, live['runners'][1]['runnerName'])]:
                        for odd in outcomes['rc'][index]['bdatb']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Back (Bet For) - ' + yn + \
                                ' - Asian Handicap'
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2, index
                            )

                        for odd in outcomes['rc'][index]['bdatl']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Lay (Bet Against) - ' + \
                                yn + ' - Asian Handicap'
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2, index
                            )

                elif market_type == 'CORRECT_SCORE':
                    for index, yn in [(0, '0-0'), (1, '0-1'), (2, '0-2'), (3, '0-3'),
                                      (4, '1-0'), (5, '1-1'), (6,
                                                               '1-2'), (7, '1-3'),
                                      (8, '2-0'), (9, '2-1'), (10,
                                                               '2-2'), (11, '2-3'),
                                      (12, '3-0'), (13, '3-1'), (14,
                                                                 '3-2'), (15, '3-3'),
                                      (16, 'Any Other Home Win'), (17, 'Any Other Away Win'), (18, 'Any Other Draw')]:
                        for odd in outcomes['rc'][index]['bdatb']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Back (Bet For) - ' + yn + \
                                ' - Asian Handicap'
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2, index
                            )

                        for odd in outcomes['rc'][index]['bdatl']:
                            if odd['odds'] == 0:
                                continue
                            name = market_name + ' - ' + period + \
                                ' - Lay (Bet Against) - ' + \
                                yn + ' - Asian Handicap'
                            set_odd(
                                live, odd, name, period, market,
                                outcomes, competitor1, competitor2, index
                            )

    except Exception as e:
        logger.opt(exception=True).critical(
            "get_odds Ошибка преобразования API данных коэффициентов - в БД: {}", e)
        logger.error('API данные лайв игры:\n' + str(live['event']['name']))
        print(e, type(e))


def main():
    start_time = time()
    # cur = bd.cur
    bd.clear_koef(bk_name)  # очищаем БД
    logger.debug('БД очищена...')
    while True:  # Бесконечный цикл, выход по ctrl+c
        logger.debug("")
        if not check_site_status():
            print('Site under maintenance, sleep 300 sec')
            sleep(300)
            continue
        while_time = time()
        request_start_time = time()
        active_live = get_active_live_games(headers)
        request_end_time = time()

        try:
            logger.debug('Обработка live игр...')
            getter_start_time = time()
            for index, live in enumerate(active_live, 1):
                print(f'=== game № {index} ===')
                print(live)
                # проверка на нужные нам виды спорта
                if not active_sport.get(int(live['eventType']['id'])):
                    continue
                setter_start_time = time()
                # получаем словари и пишем их в БД
                get_live(live)
                # получаем кэфы и записываем их в БД
                get_odds(live, headers)
                setter_end_time = time()
                print(f"Время записи в БД {round(setter_end_time - setter_start_time)} (сек)")
            getter_end_time = time()
            print(f"Время цикла перебора всех игр {round(getter_end_time - getter_start_time)} (сек)")
            if round(time() - while_time) > 5:
                logger.error('Цикл работал больше 5 сек.')
        except Exception as e:
            logger.opt(exception=True).error(
                "Ошибка во время выполнения цикла: {}", e)
        break


# подключаемся к БД
while bd.connect():
    logger.error("ERROR! - No connect BD")
    sleep(60)
cur = bd.cur
session = requests.Session()
token = get_token()
# print(token)
headers = {
    'cache-control': 'no-cache',
    'content-type': 'application/json;charset=UTF-8',
    'origin': 'https://orbitexch.com',
    'referer': 'https://orbitexch.com/customer/inplay/all/1',
    'user-agent': bd.user_agent_rand(),
    'x-csrf-token': token,
    'x-device': 'DESKTOP',
    'x-requested-with': 'XMLHttpRequest',
}

bk_name = 'orbitexch_com'
bk_id = str(bd.get_bk_id(bk_name))
active_sport = bd.active_sport(bk_name)

if __name__ == '__main__':
    while True:
        try:
            main()
        except UnicodeEncodeError:
            print('loop -> UnicodeEncodeError')
            print('Sleep 5')
            sleep(5)
            continue
        except KeyboardInterrupt:
            bd.cur.close()
            bd.conn.close()
            logger.info('Скрипт остановлен')
            break
