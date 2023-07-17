#!/usr/bin/python3
# -*- coding: utf-8 -*-
# парсер Olimp.com, Pool 20 процессов
import os
import re
import sys
import time
import random
import urllib3
import hashlib
import logging
import requests
import datetime
import traceback
import lxml.html as html
from loguru import logger
from multiprocessing import Pool
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
appPath = os.path.abspath(os.path.dirname(os.path.join(sys.argv[0])))
inifile = os.path.dirname(appPath) + "scaner"
sys.path.insert(0, inifile)
import bd_scaner as scaner


# logger.add('log_olimp.log', format="{time} {level} {message}", level='DEBUG')

bk_name = 'olimp_com'
timeout = 30
restart_time_pars = 4
liga_info = {}
gamer_info = {}
info_koef = {}

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('log_olimp_com.log')
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# подключение к БД
while scaner.connect():
    print("ERROR! - No connect BD")
    logger.info("ERROR! - No connect BD")
    time.sleep(60)
cur = scaner.cur

DOMAIN = scaner.get_domain(bk_name)
active_sport = scaner.active_sport(bk_name)
bk_id = str(scaner.get_bk_id(bk_name))
proxy_list = scaner.proxy()  # получение списка прокси


def get_html(data: dict):
    '''получение контента веб-страницы'''
    with requests.Session() as session:
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
            "content-length": "0",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://olimp.com",
            "referer": 'https://olimp.com/betting',
            "user-agent": data['user_agent'],
            "x-requested-with": "XMLHttpRequest",
        }
        url = data['url']
        proxy = data['proxy']
        session.proxies = proxy
        session.headers = headers
        time.sleep(0.02)
        response = ''
        try:
            response = session.get(
                url, allow_redirects=False, stream=False, verify=False)
            if response.status_code != 200:
                print(f'* get_html status_code-> {response.status_code}')
            response.encoding = 'utf-8'
        except Exception as er:
            print(f'* Error get_html -> {er}, {type(er)}')
            logger.info(f'* Error get_html -> {traceback.format_exc()}')
        finally:
            return response


def get_main_content(response, DOMAIN: str) -> list:
    '''
    # получение информации о всех играх в лайве
    '''
    try:
        if not response:
            return False  # плохой прокси, заходим по-новой
        htmlBODY = html.fromstring(response.text)
        elem = htmlBODY.xpath("//td[contains(@class,'liveMainSport')]")
        sportArr = {}
        for sportEl in elem:
            sport_id = sportEl.get('data-sport')
            sport_name = sportEl.text_content()
            sport_name = sport_name.replace('  ', '')
            sport_name = sport_name.replace('\n', '')
            sport_name = sport_name.strip()
            sport_name = sport_name.split(' (')[0]
            sportArr[sport_id] = sport_name
        elem = htmlBODY.xpath("//tr[contains(@class,'forLiveFilter')]")
        gamerArr = {}
        gamer_arr_list = []
        for gamerEl in elem:
            sport_id = gamerEl.get('data-sport')
            if sport_id in sportArr:
                gamer_name = gamerEl.xpath(".//a[@class='l-name-tab ']")
                if len(gamer_name) > 0:
                    gamer_id = gamer_name[0].get('id')
                    gamer_id = gamer_id.replace('match_live_name_', '')
                    gamer_name = gamer_name[0].text_content()
                    gamer_name = gamer_name.replace('  ', '')
                    gamer_name = gamer_name.replace('\n', '')
                    gamer_name = gamer_name.strip()

                    href = gamerEl.xpath(".//a[@class='l-name-tab ']/@href")[0]
                    game_url = f'{DOMAIN}{href}'

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
    except Exception as er:
        logger.warning(f"get_main_cntnt Error -> {er}, {type(er)}")
        raise
    return gamer_arr_list


def game_page_content(game_arr: dict) -> dict:
    '''получение всей информации по отдельной игре'''
    url = game_arr['url']
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        "Connection": "keep-alive",
        "Content-Length": "0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://olimp.com",
        "Referer": 'https://olimp.com/betting',
        "User-Agent": game_arr['user_agent'],
        "X-Requested-With": "XMLHttpRequest",
    }
    proxy = game_arr['proxy']
    sport_id = game_arr['sport_id']
    bk_id = game_arr['bk_id']
    data = {}
    patt_spaces2 = re.compile('\s{2,}')
    patt_spaces3 = re.compile('\s{3,}')
    with requests.Session() as session:
        t_start = time.perf_counter()
        session.proxies = proxy
        session.headers = headers
        time.sleep(0.01)
        try:
            response = session.get(
                url, allow_redirects=False, stream=False, verify=False)
            response.encoding = 'utf-8'
        except ConnectionResetError:
            print('Ошибка соединения')
            return data  # возвращает в Пулл пустой словарь
        except Exception as er:
            print('Error game_page_content', er, type(er))
            return data  # возвращает в Пулл пустой словарь
        html_body = html.fromstring(response.text)
        try:
            koef_table = html_body.xpath("//table[@class='koeftable2']")[0]
        except Exception:
            # возникает при закрытии игры
            logger.warning(f"ERROR -> {game_arr['src_url']}")
            return

        try:
            start_g = koef_table.xpath(".//td")[0].text_content()
            started_at = re.sub(r'[^\d\.\:\ ]', '', start_g)
        except Exception:
            started_at = ''

        try:
            game_id = koef_table.xpath(".//a/img/@id")[0]
            game_id = game_id.replace('i', '')  # id игры
        except Exception:
            game_id = ''

        try:
            info_liga_list = html_body.xpath(
                "//*[contains(@class, 'ishodRollTitle')]")[0].text_content().split('.')[1:]
            info_liga = ''.join(info_liga_list).strip()
            if 'Киберфутбол' in info_liga:
                info_liga = info_liga.replace('Футбол', '')
            elif 'Кибербаскетбол' in info_liga:
                info_liga = info_liga.replace('Баскетбол', '')
            info_liga = info_liga.replace('\n', '').strip()  # название лиги
        except Exception:
            info_liga = ''

        db_sport_id = ''
        if 'Киберфутбол' in info_liga:
            db_sport_id = '7'
        elif 'Кибербаскетбол' in info_liga:
            db_sport_id = '9'
        else:
            db_sport_id = game_arr.get('db_sport_id')

        try:
            liga_id = html_body.xpath(
                "//*[@class='show_all_odds']/@data-champ_id")[0]
        except Exception:
            liga_id = ''

        try:
            # текущий счет и время игры
            score_str = koef_table.xpath(
                "//*[@class='txtmed' and @style='color:red; white-space: nowrap;']")[0].text
        except Exception:
            score_str = ''

        if score_str:
            time_game, period, comment, score = configure_period_time_score(
                score_str, sport_id)
        else:
            time_game, period, comment, score = '', '', '', ''

        try:
            gamer_name = koef_table.xpath(
                ".//*[contains(@id, 'match_live_name')]")[0].text_content()  # название игры
            gamer1 = gamer_name.split(' - ')[0].strip()  # первый игрок
            gamer2 = gamer_name.split(' - ')[1].strip()  # второй игрок
        except Exception as er:
            logger.warning(f'Error gamer_name -> {er}, {type(er)}')
            gamer_name = ''
            gamer1 = ''
            gamer2 = ''

        full_koef_list = []
        try:
            basic_koef_list_src = []
            basic_tags = koef_table.xpath(".//div[@class='tab']/nobr")
            for tag in basic_tags:
                k_name = tag.xpath(
                    './/span[@class="googleStatIssueName"]')[0].text_content()
                k_res = tag.xpath(".//*[contains(@id, 'googleStatKef')]")
                if 'Тот(' in k_name:
                    k_name_1 = f'{k_name} М'
                    k_name_2 = f'{k_name} Б'
                    data_k1 = {k_name_1: k_res[0].text_content()}
                    data_k2 = {k_name_2: k_res[1].text_content()}
                    basic_koef_list_src.append(data_k1)
                    basic_koef_list_src.append(data_k2)
                else:
                    data_k = {k_name: k_res[0].text_content()}
                    basic_koef_list_src.append(data_k)
            if basic_koef_list_src:
                data_k = {'Основные': basic_koef_list_src}
            else:
                data_k = {}
            full_koef_list.append(data_k)
            groupNames = html_body.xpath("//div[@data-match-id-show]/b")
            for index, groupName in enumerate(groupNames, 1):
                groupName_txt = groupName.text_content()
                groupName_txt = re.sub(':$', '', groupName_txt)
                # берем все одноуровневые теги nobr после нужного groupName
                group_odds = html_body.xpath(f"//div[@data-match-id-show]/b/following-sibling::nobr[count(preceding-sibling::b)={index}]")
                add_koef_list_src = []
                for odd in group_odds:
                    try:
                        if odd is not None:
                            odd_text = odd.text_content()
                            koef_name = ''
                            # один или два кэфа
                            k_res_list = odd.xpath(
                                ".//*[contains(@id, 'googleStatKef')]")
                            zTruS = True
                            try:
                                zTru = odd.xpath(
                                    ".//span[@class='googleStatIssue']")[0]
                            except Exception:
                                zTruS = False
                            if zTruS:
                                # если у ставки есть googleStatIssue
                                k_name = zTru.xpath(
                                    './/span[@class="googleStatIssueName"]')[0].text_content()
                                if len(k_res_list) == 1:
                                    # обрабатываются ставки с одним кэфом
                                    koef_name = k_name
                                    data = {koef_name: k_res_list[0].text}
                                    add_koef_list_src.append(data)
                                elif len(k_res_list) == 2:
                                    # ставки с двумя кэфами
                                    k_name = ''.join(k_name).strip().replace(
                                        '\xa0', '').replace('\n', ' ')
                                    spaces = re.findall(
                                        patt_spaces2, k_name)[0]
                                    # делим строку на две ставки по 2+ пробелам
                                    try:
                                        # если один двойной пробел
                                        k_name1, k_name2 = k_name.split(spaces)
                                    except Exception:
                                        # если двойной пробел не один
                                        k_name_list = k_name.split('  ')
                                        k_name1 = ''.join(k_name_list[:2])
                                        k_name2 = ''.join(k_name_list[2:])
                                    # оставляем только имя ставки
                                    k_name1 = k_name1.split(' -')[0].strip()
                                    k_name2 = k_name2.split(' -')[0].strip()
                                    if k_name1.endswith('-') and k_name2.endswith('-'):
                                        k_name1 = k_name1[:-1]
                                        k_name2 = k_name2[:-1]
                                    k_name1 = k_name1.strip().replace(
                                        '\xa0', '').strip()
                                    k_name2 = k_name2.strip().replace(
                                        '\xa0', '').strip()
                                    data1 = {k_name1: k_res_list[0].text}
                                    add_koef_list_src.append(data1)
                                    data2 = {k_name2: k_res_list[1].text}
                                    add_koef_list_src.append(data2)
                            # ставки без googleStatIssue - с двумя кэфами
                            else:
                                koef_all_name = odd.text_content().strip()
                                # вид "Обе забьют: да -  3.8   Обе забьют: нет
                                # -  1.2"
                                spaces = re.findall(
                                    patt_spaces3, koef_all_name)[0]
                                koef_list = koef_all_name.split(spaces)
                                if len(koef_list) == 2:
                                    koef_name1 = koef_list[
                                        0].replace('\xa0', '')
                                    koef_name2 = koef_list[
                                        1].replace('\xa0', '')
                                    # оставляем только имя ставки
                                    koef_name1 = koef_name1.split(
                                        ' -')[0].strip()
                                    koef_name2 = koef_name2.split(
                                        ' -')[0].strip()
                                    data1 = {koef_name1: k_res_list[0].text}
                                    add_koef_list_src.append(data1)
                                    data2 = {koef_name2: k_res_list[1].text}
                                    add_koef_list_src.append(data2)
                                else:
                                    # вид "Обе забьют: да -  3.8"
                                    koef_name = koef_all_name.split(
                                        ' - ')[0].strip()
                                    data = {koef_name: k_res_list[0].text}
                                    add_koef_list_src.append(data)
                    except IndexError:
                        continue
                    except Exception as er:
                        logger.warning(f'* Error group_odds -> {er}, {type(er)}')
                        continue
                data = {groupName_txt: add_koef_list_src}
                full_koef_list.append(data)
        except Exception:
            logger.warning(f"Err full_koef_list >>> {er} {type(er)}")
            full_koef_list = []
        try:
            data = {
                'started_at': started_at.strip(),
                'bk_id': bk_id,
                'sport_id': sport_id,
                'db_sport_id': db_sport_id,
                'champ': info_liga,
                'liga_id': liga_id,
                'game_id': game_id,
                'game_url': game_arr['src_url'],
                # 'game_url': game_arr['url'],
                'time_game': time_game,
                'score': score,
                'period': period,
                'comment': comment,
                'gamer_name': gamer_name.strip(),
                'gamer1': gamer1,
                'gamer2': gamer2,
                'koef_list': full_koef_list,
            }
        except Exception as er:
            logger.warning(f'* Error data -> {er}, {type(er)}')
        t_end = time.perf_counter()
        if round(t_end - t_start, 2) > 10:
            print(
                f'Прокси {ip}:{port} - время обработки {round(t_end - t_start, 2)}')
            logger.info(
                f'Прокси {ip}:{port} - время обработки {round(t_end - t_start, 2)}')
        return data


def configure_period_time_score(score: str, sport_id: str) -> str:
    '''возвращает период, время матча, счет и комментарий'''
    time_game = ''
    period = ''
    score_ = score
    if '"' in score:
        time_game = score.split('"')[0].split()[-1]
        time_game = time_game.replace('<', '')
        score_ = score.split('"')[0].rsplit(maxsplit=1)[0]
        if 'Счет' in score_:
            score_ = score_.split('Счет')[0]
        elif 'Перерыв' in score_:
            score_ = score_.split('Перерыв')[0]
    elif ('PAUSE' in score) or ('Перерыв' in score):
        time_game = 'Break'
        score_ = score.split('Перерыв')[0]
        if 'Счет' in score_:
            score_ = score_.split('Счет')[0]
    elif ('Матч не начался' in score):
        time_game = 'Not start'
        score_ = '0:0'
    elif ('Матч завершен' in score):
        time_game = 'Closed'
        score_ = score.replace('Матч завершен', '')
        if 'Счет' in score_:
            score_ = score_.split('Счет')[0]
    elif 'Окончание' in score:
        score_ = score.split('Окончание')[0]
    elif 'Best' in score:
        score_ = score.split('Best')[0]
    if 'Счет' in score_:
        score_ = score_.split('Счет')[0]

    if (')' in score):
        comment = score.split(')')[-1]
        comment = comment.replace(',', '').replace('<', '')
        if '"' in comment:
            comment = comment.split('"')[-1]
    else:
        if '"' in score:
            comment = score.split('"')[-1].replace(',', '')
        else:
            comment = ''

    if sport_id == '1':  # football
        if '+' in time_game:
            if int(time_game.split('+')[0]) > 45:
                period = '2 time'
            else:
                period = '1 time'
        elif time_game.isdigit():
            if int(time_game) > 45:
                period = '2 time'
            else:
                period = '1 time'
        else:
            period = time_game
    elif (sport_id == '6') or (sport_id == '11') or (sport_id == '136'):
        # american football, futsal, basketball_3x3
        g = score.split(':')
        if str(len(g) - 2) == '0':
            period = '1 time'
        else:
            period = str(len(g) - 2) + ' time'
    # tennis, table_tennis, volleyball, badminton
    elif (sport_id == '3') or (sport_id == '40') or (sport_id == '10') or (sport_id == '51'):
        try:
            g = score.split(' (')[0]
            g = g.split(':')
            g = int(g[0]) + int(g[1]) + 1
            period = str(g) + ' set'
        except Exception:
            period = ''
    elif (sport_id == '2') or (sport_id == '141'):  # hockey, cyberhockey
        g = score.split(':')
        if str(len(g) - 2) == '0':
            period = '1 period'
        else:
            period = str(len(g) - 2) + ' period'
    elif (sport_id == '5') or (sport_id == '140'):
        # basketball, cyberbasketball
        g = score.split(':')
        if str(len(g) - 2) == '0':
            period = '1 quarter'
        else:
            period = str(len(g) - 2) + ' quarter'
    elif sport_id == '112':  # esport
        if (',' in score):
            period = f"{len(score.split(','))} map"
        else:
            period = '1 map'

    score_ = score_.replace('),', ')')
    score_ = score_.replace(') ,', ')')
    score_ = score_.replace('   ', ' ')
    score_ = score_.replace('  ', ' ')
    return time_game, period, comment, score_


def get_all_game_content(game_info: dict) -> dict:
    '''извлечение всех данных об одной игре и формирование словарей'''
    liga_id = game_info['liga_id']
    liga = game_info['champ']
    bk_id = game_info['bk_id']
    sport_id = str(game_info['db_sport_id'])
    id_liga_hash = hashlib.md5(
        (str(liga_id) + bk_name).encode('utf-8')).hexdigest()

    game_id = game_info['game_id']
    gamer1 = game_info['gamer1'].strip()
    gamer2 = game_info['gamer2'].strip()
    gamer_name = game_info['gamer_name'].strip()
    bk_id_gamer1 = 0
    bk_id_gamer2 = 0
    started_at = game_info.get('started_at')
    if started_at:
        started_at = datetime.datetime.strptime(
            started_at, '%d.%m.%Y %H:%M').timestamp()
    else:
        started_at = ''
    time_game = game_info['time_game']
    score = game_info['score']
    comment = game_info['comment']
    state = game_info['period']
    link = game_info['game_url']

    id_game_hash = hashlib.md5(
        (str(game_id) + gamer1 + gamer2 + bk_name).encode('utf-8')).hexdigest()
    gamer_info_1 = hashlib.md5(
        (gamer1 + str(sport_id) + bk_name).encode('utf-8')).hexdigest()
    gamer_info_2 = hashlib.md5(
        (gamer2 + str(sport_id) + bk_name).encode('utf-8')).hexdigest()

    if ('УГЛ ' in gamer1) or ('ЖК ' in gamer1) or (' (штанги и перекладины)' in gamer1) or (' (удары в створ)' in gamer1) or (' (офсайды)' in gamer1) or (' (фолы)' in gamer1) or ('удалений' in gamer1) or ('голы в больш' in gamer1):
        return
    liga_info[id_liga_hash] = {
        'liga': liga,
        'sport_id': sport_id,
        'bk_id_liga': liga_id,
        'live_is': '1'}
    gamer_info[id_game_hash] = {
        'bk_name': bk_name,
        'id_liga_hash': id_liga_hash,
        'bk_id_gamer1': bk_id_gamer1,
        'bk_id_gamer2': bk_id_gamer2,
        'gamer1': gamer1,
        'gamer2': gamer2,
        'time_game': time_game,
        'score': score,
        'started_at': started_at,
        'sport_id': sport_id,
        'state': state,
        'link': link,
        'game_id': game_id,
        'gamer_info_1': gamer_info_1,
        'gamer_info_2': gamer_info_2,
        'name': gamer_name,
        'bk_id': bk_id,
        'liga_info': id_liga_hash,
        'gamer_id_bk': game_id,
        'created_at': '',
        'update_at': '',
        'comment': comment,
    }
    # print(gamer_info)
    koef_list = game_info['koef_list']
    for bets_type_dict in koef_list:
        for groupName, bet_list in bets_type_dict.items():
            groupName = groupName
            if ('Гонка' in groupName) or ('Овертайм' in groupName) or ('Счёт ' in groupName) or ('Счет ' in groupName) or ('чет/нечет' in groupName) or ('Следующее' in groupName) or ('Самая' in groupName) or ('Ставки' in groupName) or ('оличество' in groupName) or ('Счет:' in groupName) or ('Счёт:' in groupName) or ('Голы' in groupName) or ('Результативность ' in groupName) or ('Следующий' in groupName) or ('Время' in groupName) or ('Точный' in groupName) or ('Разница' in groupName) or ('Самый' in groupName) or ('Результат' in groupName) or ('в периодах' in groupName) or ('минимум' in groupName) or ('Как будут' in groupName):
                continue

            patt_total = re.compile(r'[Тт]отал')
            patt_fora = re.compile(r'форой')
            patt_param = re.compile(r'(?<=\()([\d\W]+?)(?=\))')
            game_live = hashlib.md5(
                (str(game_id) + gamer1 + gamer2 + bk_name).encode('utf-8')).hexdigest()

            if game_live not in gamer_info:
                continue
            for bets in bet_list:
                for key, value in bets.items():
                    bet_short = key.strip()

                    if (gamer1 in bet_short) or (gamer2 in bet_short):
                        bet_short = bet_short.replace(
                            gamer1, 'К1').replace(gamer2, 'К2')

                    if re.findall(patt_param, key):
                        param = re.findall(patt_param, key)[0]
                        bet_short_param = bet_short
                        bet_short = bet_short.replace(f'({param})', '()')
                        bet_param = f"({param})"
                    else:
                        param = 'NULL'
                        bet_short = bet_short
                        bet_short_param = bet_short
                        bet_param = ''

                    bet_short = bet_short.split()
                    bet_short = '_'.join(bet_short)
                    bet_short_param = bet_short_param.split()
                    bet_short_param = '_'.join(bet_short_param)
                    sport_name = liga.split()[0]
                    if sport_name == 'Американский':
                        sport_name = 'Американский Футбол'
                    elif sport_name == 'Настольный':
                        sport_name = 'Настольный Теннис'
                    if groupName == 'Основные':
                        short_name = f"{sport_name}. Match {bet_short}"
                        name = f"Match {bet_short_param}"
                    elif ('-й ' in groupName) or ('-я ' in groupName) or ('-го ' in groupName) or ('партии:' in groupName) or ('половинах:' in groupName) or ('й сет' in groupName) or ('Карта ' in groupName) or ('половинам:' in groupName) or ('четвертя' in groupName) or ('в четвертях:' in groupName) or ('период:' in groupName) or ('по таймам' in groupName):
                        short_name = f"{sport_name}. {groupName} {bet_short}"
                        name = f"{groupName} {bet_short_param}"
                    else:
                        short_name = f"{sport_name}. Match {groupName} {bet_short}"
                        name = f"Match {groupName} {bet_short_param}"
                    koef = value
                short_name = short_name.split('_-_')[0]
                kof_hash = hashlib.md5(
                    (str(game_id) + short_name + bk_id + param).encode('utf-8')).hexdigest()
                name_hash = hashlib.md5(
                    (short_name + bk_id).encode('utf-8')).hexdigest()
                comment = short_name
                dop = {
                    'id': game_id,
                    'groupName': groupName,
                    'name': name,
                    'short_name': short_name,
                    'koef': koef,
                    'param': param,
                    'original': key,
                    'link': link
                }
                name_koef_id = hashlib.md5(
                    (str(game_id) + str(name) + str(koef) + bk_id).encode('utf-8')).hexdigest()

                info_koef[kof_hash] = {
                    "game_live": game_live,
                    "bk_id": str(bk_id),
                    "game_orig": str(game_id),
                    "name": name,
                    "short_name": short_name,
                    "koef": koef,
                    "id": game_id,
                    "name_hash": name_hash,
                    "comment": comment,
                    'p_name': state,
                    "param": param,
                    "dop": str(dop),
                    "name_koef_id": name_koef_id,
                    "groupName": groupName,
                    "created_at": '',
                    "update_at": '',
                }


def main():
    try:
        time1 = datetime.datetime.now()
        with open('log_olimp_com.log', 'w'):
            pass
        logger.info("Start olimp_com")
        scaner.clear_koef(bk_name)
        print('БД очищена...')
        print(f"Start: {datetime.datetime.now()}")
        print(f"DOMAIN: {DOMAIN}")
        MAIN_URL = f'{DOMAIN}ajax_index.php?page=line&live=1'
        print(f"MAIN_URL: {MAIN_URL}")
        work = True
        while work:
            try:
                print('-----------------------')
                response_data = {}
                t_start = time.perf_counter()
                user_agent = scaner.user_agent_rand()
                n = random.randint(0, len(proxy_list) - 1)
                ip = proxy_list[n][1]
                port = proxy_list[n][2]
                login = proxy_list[n][3]
                password = proxy_list[n][4]
                http = f'http://{login}:{password}@{ip}:{port}'
                proxy = {
                    'http': http,
                    'https': http,
                }
                response_data = {
                    'url': MAIN_URL,
                    'user_agent': user_agent,
                    'proxy': proxy,
                }
                response = get_html(response_data)
                sports = get_main_content(response, DOMAIN)
                if not sports:
                    print(f'sports: {sports}')
                    continue  # плохой прокси, начинаем сначала
                print(f'Всего live-игр {len(sports)}')
                pool_arr = []
                for sport in sports:
                    # формирование словаря по отдельному матчу для Pool
                    sport_id = sport['sport_id']
                    if int(sport_id) not in active_sport:
                        continue
                    src_url = sport['game_url']
                    url = f"{DOMAIN}/ajax_index.php?page=line&line_nums=0&action=2&mid=0&id=0&live[]={sport['gamer_id']}&sid[]={sport_id}"
                    db_sport_id = str(active_sport.get(int(sport_id)))
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
                    user_agent = scaner.user_agent_rand()
                    game_arr = {
                        'url': url,
                        'src_url': src_url,
                        'proxy': proxy,
                        'user_agent': user_agent,
                        'sport_id': sport_id,
                        'db_sport_id': db_sport_id,
                        'bk_id': bk_id
                    }
                    pool_arr.append(game_arr)
                with Pool(20) as pool:
                    try:
                        result = pool.map(game_page_content, pool_arr)
                        now = datetime.datetime.now()
                        print(str(now) + ' - Обработка результатов потока')
                    except Exception:
                        pass
                # pool.map возвращает список (словарей) из всех процессов
                try:
                    for data in result:
                        if len(data) > 0:
                            get_all_game_content(data)
                        else:
                            print('Пустой результат!')
                except Exception as er:
                    scaner.clear_koef(bk_name)
                    print('Error обработки result', er, type(er))
                    continue
                scaner.add_liga(liga_info, bk_id)
                scaner.add_gamer(gamer_info, bk_id, bk_name)
                scaner.add_koef_olimp_com(info_koef, bk_id)
                t_end = time.perf_counter()
                print(f'Цикл обработки игр {round(t_end - t_start, 2)}')
            except KeyboardInterrupt:
                print('Main - Скрипт остановлен')
                scaner.cur.close()
                scaner.conn.close()
                break
            except Exception as er:
                print('*** Main Loop Error ***', er, type(er))
                continue
            finally:
                gamer_info.clear()
                liga_info.clear()
                info_koef.clear()
    except Exception:
        pass


if __name__ == '__main__':
    while True:
        try:
            main()
            time.sleep(restart_time_pars)
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
            print('Loop - Скрипт остановлен')
            scaner.cur.close()
            scaner.conn.close()
            break
        except Exception:
            logger.info(traceback.format_exc())
            time.sleep(restart_time_pars)
            raise
            continue
