# !/usr/bin/env python3
# -*- coding: utf-8 -*-

# import os
# import re
# from shutil import ExecError
# import sys
import time
import json
# import urllib
# import random
import pickle
import requests
import websocket
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# from python3_anticaptcha import NoCaptchaTaskProxyless
# from fake_useragent import UserAgent

import ggbet_settings


class Ggbet:

    """бот для ggbet.ru"""

    def __init__(self, login, password, domain):
        self.login = login
        self.password = password
        self.domain = domain

    def setup_method(self):
        ''' инициализация драйвера '''
        # убираем детект Селениума
        options = webdriver.ChromeOptions()
        # ua = UserAgent()
        # user_agent = ua.random
        # print(user_agent)
        # options.add_argument(f'user-agent={user_agent}')
        options.add_experimental_option('useAutomationExtension', False)
        # убирает "Браузером управляет Тестовое ПО"
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"])
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }  # убирает предложение о сохранении пароля
        options.add_experimental_option("prefs", prefs)
        options.add_argument('--disable-notifications')
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-save-password")
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("disable-infobars")
        options.add_argument("--mute-audio")
        options.add_argument("start-maximized")
        options.add_argument('--safebrowsing-disable-extension-blacklist')
        options.add_argument('--safebrowsing-disable-download-protection')
        # Remove navigator.webdriver Flag using JavaScript
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.vars = {}

    def teardown_method(self):
        ''' закрытие браузера '''
        self.driver.quit()

    def check_loaded_page(self):
        """при открытии страниц сайта ждем полной загрузки"""
        WebDriverWait(self.driver, 10).until(lambda driver: self.driver.execute_script(
            'return document.readyState') == 'complete')

    def open_home_page(self):
        '''открываем главную страницу'''
        self.driver.get(self.domain)

    def save_cookies(self):
        ''' формируем куки-файл для следующего захода '''
        # валидны только некоторое время, потом файл нужно удалять!
        pickle.dump(self.driver.get_cookies(), open('cookies.pkl', 'wb'))

    def set_cookies(self):
        ''' загрузка кукис, если валидные - логин без капчи '''
        # невалидные крашат браузер
        try:
            cookies = pickle.load(open("cookies.pkl", "rb"))
            for cookie in cookies:
                self.driver.add_cookie(cookie)
        except FileNotFoundError:
            print('Файл cookies не найден')
        except Exception as er:
            print('set_cookies ', er, type(er))
        self.driver.refresh()

    def auth(self) -> bool:
        ''' авторизация, True/False '''
        self.check_loaded_page()
        try:
            self.driver.find_element_by_xpath(
                "//*[contains(@class, 'cookie-agreement__button--ok')]").click()
        except Exception:
            pass
        self.check_loaded_page()
        login = True
        try:
            self.driver.find_element_by_xpath(
                "//a[contains(@class, 'header-profile__logout')]")
        except Exception:
            login = False
        # если после загрузки кукис все еще не залогинились
        if not login:
            try:
                self.check_loaded_page()
                # ждем, когда username будет кликабельным
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                    (By.ID, "_username"))).send_keys(self.login)
                self.driver.find_element_by_id(
                    "_password").send_keys(self.password)
                frames = self.driver.find_elements_by_tag_name("iframe")
                recaptcha_control_frame = None
                for index, frame in enumerate(frames):
                    if frame.get_attribute("title") == "reCAPTCHA":
                        recaptcha_control_frame = frame
                # переключаемся на рекапчу в iframe
                WebDriverWait(self.driver, 10).until(
                    EC.frame_to_be_available_and_switch_to_it(
                        recaptcha_control_frame)
                )
                WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//span[contains(@class, 'recaptcha-checkbox')]"
                        )
                    )
                ).click()
                self.check_loaded_page()
                try:
                    time.sleep(15)  # ввод капчи вручную
                    # выбираем нужные картинки и жмем Подтвердить
                    self.driver.switch_to.default_content()
                    WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(@class, 'sign-in__b-button')]"))).click()
                    login = True
                except Exception as ex:
                    print('Ручной ввод капчи неудачен')
                    print(ex, type(ex))
            except Exception as ex:
                print(ex, type(ex))
        time.sleep(2)
        self.check_loaded_page()
        if login:
            print('Залогинились')
        else:
            print('Не залогинились')
        return login

    def get_balance(self) -> float or bool:
        ''' получаем доступный баланс '''
        self.check_loaded_page()
        try:
            balance = self.driver.find_element_by_xpath(
                "//span[@class='header-balance__value']/span").text
            balance = round(float(balance), 2)
        except NoSuchElementException as err:
            print(err, 'Баланс не найден')
            balance = False
        print('balance', balance)
        self.balance = balance
        return balance

    def enter_live(self) -> bool:
        ''' заходим в лайв игры '''
        try:
            self.driver.find_element_by_xpath("//a[@href='/live']").click()
            print('Зашли в live')
            self.check_loaded_page()
            return True
        except Exception:
            print('Не удается открыть live')
            self.check_loaded_page()
            return False

    def run_websocket(self) -> str:
        ''' подключение к вебсокету '''
        while True:
            header = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4612.0 Safari/537.36'}
            ws = websocket.WebSocket()
            ws.connect(
                "wss://b-gql.ggbet.ru/graphql",
                subprotocols=["graphql-ws"],
                header=header,
            )
            # инициализация подключения
            print('--- connection init ------->>>>>>>>>>')
            message_init = json.dumps(
                {
                    "type": "connection_init",
                    "payload": {
                        "headers": {
                            "X-Auth-Token": "8d4Siwg6WwcU35n--Nq-oUxip5cT5fbkAgwIeKsuKbgFcqlNZ0yy00KLZsVxdNf32IukPDgwc0TG8zQwUqU7obxeP98MCQRS2OYv9d741QTA8GvTshYaZNwCbKewjADKLAyMnpIVHioJnHA4YV7h8HDd80-aBy9h7CifhMcObVeUyjI-4JqM1ROnGqRv-v9JA5h51qRff2m26qrFV4KZR9PQgOqTVTYua7iq-AqiHcZe784L_fVGW9pAPVfcsf9oURJKnVbJ1rALMPU85nAucE_OVYTZMkK_fHzfVYlj2sVw8JFi1apUAo6cZLOyJrq3bmp6W9UOonnUKNmrGJLmKDcDzjB8Pb1cffG_LiURapMdgq24cUk0Trf6pqqzWTAscTs4YhJ7NiZAp90KeZs-TF70YvCczB-I--IG"
                        }
                    }
                }
            )
            ws.send(message_init)
            result1 = ws.recv()
            if not result1:
                continue
            try:
                print('--- message start ------->>>>>>>>>>')
                # получение инфы о всех играх в лайве
                message_start = json.dumps(
                    {
                        "id": "1",
                        "type": "start",
                        "payload": {
                            "variables": {
                              "offset": 0,
                              "limit": 200,
                              "matchStatuses": [
                                  "LIVE",
                                  "SUSPENDED"
                              ],
                                "marketStatuses": [
                                  "ACTIVE",
                                  "SUSPENDED"
                              ],
                                "sportEventTypes": [
                                  "MATCH"
                              ],
                                "sportIds": [
                                  "esports_call_of_duty",
                                  "esports_counter_strike",
                                  "esports_dota_2",
                                  "esports_heroes_of_the_storm",
                                  "esports_league_of_legends",
                                  "esports_overwatch",
                                  "esports_starcraft",
                                  "esports_world_of_tanks",
                                  "esports_street_fighter_5",
                                  "esports_vainglory",
                                  "esports_warcraft_3",
                                  "esports_rainbow_six",
                                  "esports_rocket_league",
                                  "esports_smite",
                                  "esports_soccer_mythical",
                                  "esports_halo",
                                  "esports_crossfire",
                                  "esports_starcraft_1",
                                  "esports_king_of_glory",
                                  "esports_nba_2k18",
                                  "esports_artifact",
                                  "esports_dota_auto_chess",
                                  "esports_apex_legends",
                                  "esports_fifa",
                                  "esports_basketball",
                                  "esports_tennis",
                                  "esports_formula_1",
                                  "esports_ice_hockey",
                                  "esports_rasing",
                                  "esports_volleyball",
                                  "esports_valorant",
                                  "esports_mortal_kombat",
                                  "esports_league_of_legends_wild_rift",
                                  "football",
                                  "basketball",
                                  "tennis",
                                  "ice_hockey",
                                  "volleyball",
                                  "baseball",
                                  "beach_volleyball",
                                  "boxing",
                                  "futsal",
                                  "handball",
                                  "mma",
                                  "snooker",
                                  "motorsport",
                                  "american_football",
                                  "beach_soccer",
                                  "badminton",
                                  "table_tennis",
                                  "chess",
                                  "rugby",
                                  "rugby_league",
                                  "formula_1",
                                  "cycling",
                                  "darts",
                                  "water_polo",
                                  "biathlon",
                                  "bandy",
                                  "cross_country",
                                  "ski_jumping",
                                  "alpine_skiing",
                                  "curling",
                                  "basketball_3x3",
                                  "hockey",
                                  "olympics",
                                  "wrestling",
                                  "rowing",
                                  "canoe_slalom",
                                  "canoe_sprint",
                                  "judo",
                                  "karate",
                                  "equestrian",
                                  "sailing",
                                  "swimming",
                                  "diving",
                                  "trampoline",
                                  "surfing",
                                  "synchronized_swimming",
                                  "skateboarding",
                                  "modern_pentathlon",
                                  "softball",
                                  "artistic_gymnastics",
                                  "sport_climbing",
                                  "shooting",
                                  "archery",
                                  "triathlon",
                                  "taekwondo",
                                  "weightlifting",
                                  "fencing",
                                  "rhythmic_gymnastics",
                                  "basketball_3х3",
                                  "rugby_sevens",
                                  "athletics",
                                  "golf",
                                  "canoeing"
                              ],
                                "tournamentIds": [],
                                "marketStatusesForSportEvent": [
                                  "ACTIVE",
                                  "SUSPENDED",
                                  "RESULTED",
                                  "CANCELLED",
                                  "DEACTIVATED"
                              ],
                                "marketLimit": 200,
                                "isTopMarkets": True,
                                "order": "RANK_LIVE_PAGE",
                                "providerIds": []
                            },
                            "extensions": {},
                            "operationName": "GetMatchesByFilters",
                            "query": "query GetMatchesByFilters($offset: Int!, $limit: Int!, $search: String, $dateFrom: String, $dateTo: String, $providerIds: [Int!], $matchStatuses: [SportEventStatus!], $sportIds: [String!], $tournamentIds: [String!], $competitorIds: [String!], $marketStatusesForSportEvent: [MarketStatus!], $marketStatuses: [MarketStatus!], $marketLimit: Int = 1, $isTopMarkets: Boolean = false, $dateSortAscending: Boolean, $sportEventTypes: [SportEventType!], $withMarketsCount: Boolean = true, $marketTypes: [Int!], $favorite: Boolean = false, $hasStreams: Boolean, $order: SportEventOrder) {\n  matches: sportEventsByFilters(offset: $offset, limit: $limit, searchString: $search, dateFrom: $dateFrom, dateTo: $dateTo, providerIds: $providerIds, matchStatuses: $matchStatuses, sportIds: $sportIds, tournamentIds: $tournamentIds, competitorIds: $competitorIds, marketStatuses: $marketStatusesForSportEvent, sportEventTypes: $sportEventTypes, dateSortAscending: $dateSortAscending, marketTypes: $marketTypes, favorite: $favorite, hasStreams: $hasStreams, order: $order) {\n    ...Match\n    marketsCount(statuses: $marketStatuses) @include(if: $withMarketsCount)\n  }\n}\n\nfragment Match on SportEvent {\n  ...MatchBase\n  markets(top: $isTopMarkets, limit: $marketLimit, statuses: $marketStatuses) {\n    ...Market\n  }\n}\n\nfragment MatchBase on SportEvent {\n  id\n  disabled\n  providerId\n  hasMatchLog\n  slug\n  meta {\n    name\n    value\n  }\n  fixture {\n    ...MatchFixture\n  }\n}\n\nfragment MatchFixture on SportEventFixture {\n  score\n  title\n  status\n  type\n  startTime\n  sportId\n  liveCoverage\n  streams {\n    id\n    locale\n    url\n    platforms {\n      type\n      enabled\n    }\n  }\n  tournament {\n    ...MatchTournament\n  }\n  competitors {\n    id: masterId\n    name\n    type\n    homeAway\n    logo\n    templatePosition\n    score {\n      id\n      type\n      points\n      number\n    }\n  }\n}\n\nfragment MatchTournament on Tournament {\n  id\n  name\n  masterId\n  countryCode\n  logo\n  description\n  showTournamentInfo\n  prizePool\n  dateStart\n  dateEnd\n  isLocalizationOverridden\n  slug\n  sportId\n}\n\nfragment Market on Market {\n  ...MarketBase\n  odds {\n    ...Odd\n  }\n}\n\nfragment MarketBase on Market {\n  id\n  name\n  status\n  typeId\n  priority\n  tags\n  specifiers {\n    name\n    value\n  }\n}\n\nfragment Odd on Odd {\n  id\n  name\n  value\n  isActive\n  status\n  competitorId\n}\n"
                        }
                    }
                )
                ws.send(message_start)
                result2 = ws.recv()
                print('=== result message 1 start =========')
                return result2
            except Exception as er:
                print(er, type(er))
                print('Нет доступных игр в live, ждем 5 сек')
                time.sleep(5)
                continue

    def get_all_games(self, result: str) -> list:
        '''получение всех доступных игр в лайве'''
        try:
            result_dict = json.loads(result)
            matches = result_dict['payload']['data']['matches']
            # print(len(matches))
            gamer_arr_list = []
            for match in matches:
                sport_id = match['fixture']['sportId']
                # if not sport_id: continue
                game_id = match['id']
                slug = match['slug']
                title = match['fixture']['title']
                if 'esports' in sport_id:
                    link = f'https://ggbet.ru/esports/match/{slug}'
                else:
                    link = f'https://ggbet.ru/sports/match/{slug}'
                gamerArr = {
                    'game_id': game_id,
                    'slug': slug,
                    'title': title,
                    'link': link,
                }
                gamer_arr_list.append(gamerArr)
            # print(f'Доступно игр {len(gamer_arr_list)}')
        except Exception:
            gamer_arr_list = None
        return gamer_arr_list

    def openGameNew(self, game_name: str, dop: dict, ligaName='') -> bool:
        '''
        заходим на страницу выбранной игры
        '''
        self.check_loaded_page()
        # должна быть открыта страница live
        if self.driver.current_url != "https://ggbet.ru/live":
            print('Страница не лайв!')
            self.enter_live()
        # получаем все доступные игры live
        result = self.run_websocket()
        all_games = self.get_all_games(result)
        if all_games:
            print(len(all_games), 'игр всего сейчас в лайв')
            print("Ищем игру", game_name)
            for game in all_games:
                try:
                    if game_name != game['title']:
                        continue
                    game_url = game['link']
                    self.driver.get(game_url)
                    break
                except Exception as er:
                    print(er, type(er))
        self.check_loaded_page()
        # проверка: открыта ли та игра, что нужно
        if game_url == self.driver.current_url:
            self.dop = dop
            print('Игра найдена правильно')
            return True
        else:
            print('Игра не найдена')
            return False

    def clearCupon(self) -> bool:  # +
        ''' очистка купона от всех выбранных коэффициентов '''
        # сначала проверяем открыт ли купон
        if not self.check_open_coupone():
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
            time.sleep(1)
        coupon_btns = self.driver.find_elements_by_xpath(
            "//*[contains(@class, '__app-Tabs-tab')]/div")
        for btn in coupon_btns:
            if btn.get_attribute('innerText') == 'КУПОН ПАРИ':
                btn.click()
        # в купоне ищем кнопку отмены - крестик
        try:
            cross = self.driver.find_element_by_xpath(
                "//*[name()='use' and @*[contains(., '#close-video')]]")
            if cross.is_displayed():
                close_btns = self.driver.find_elements_by_xpath(
                    "//*[name()='use' and @*[contains(., '#close-video')]]")
                for btn in close_btns:
                    btn.click()
                print('Купон очищен')
        except Exception:
            print('Кнопка очистки не найдена, купон чист')
        # закрываем купон в конце
        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
        return True

    def openCupon(self, max_error=3) -> dict or bool:  # +
        '''
        выбор нужной ставки на странице игры,
        данные берутся из self.dop
        {"id":69307978,
        "groupName": "1 тайм - Пхохан Стилерс тотал голов",
        "name": "Over 0.5",  "Under 0.5: 1.28"
        "short_name": "",
        "koef": 3.72,
        "param": "0.5"}
        '''
        self.check_loaded_page()
        self.clearCupon()  # очищаем купон
        odds = self.driver.find_elements_by_xpath(
            "//*[contains(@class, 'tableHeader__container')]")  #
        print(f'Всего ставок для игры найдено {len(odds)}')
        dop = self.dop
        exit_flag = False
        self.driver.implicitly_wait(5)
        for index, odd in enumerate(odds):
            try:
                # groupName
                title = odd.find_element_by_xpath(
                    ".//div[contains(@class, 'marketTable__header')]").get_attribute('title')
                if title != dop['groupName']:
                    continue
                bets = odd.find_elements_by_xpath(
                    ".//*[contains(@class, 'tableMarketRow') and not(contains(@class, 'container'))]")
                for bet in bets:
                    try:
                        odd_str = bet.find_element_by_xpath(
                            ".//button[@data-analytics-info='bet_add']").get_attribute('title')
                        koef_name = odd_str.split(':')[0]
                        if koef_name != dop['name']:
                            continue
                        print(f"{koef_name} = {dop['name']}")
                        bet.find_element_by_xpath(
                            ".//*[@data-analytics-info='bet_add']").click()
                        exit_flag = True
                        break
                    except NoSuchElementException:
                        pass
                    except Exception as er:
                        print('openCupon 1 ', er, type(er))
                if exit_flag:
                    break
            except Exception as er:
                print('openCupon 2 ', er, type(er))
        # проверка появилась ли в купоне ставка
        self.check_loaded_page()
        # открываем купон
        if not self.check_open_coupone():
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
        coupon_btns = self.driver.find_elements_by_xpath(
            "//*[contains(@class, '__app-Tabs-tab')]/div")
        for btn in coupon_btns:
            if btn.get_attribute('innerText') == 'КУПОН ПАРИ':
                btn.click()
        try:
            coupon_title = self.driver.find_element_by_xpath(
                "//*[contains(@class, '__app-OddDetails-market')]").get_attribute('title')
            coupon_name = self.driver.find_element_by_xpath(
                "//*[contains(@class, '__app-OddDetails-team')]").get_attribute('title')
        except Exception:
            coupon_title = ''
            coupon_name = ''
        if coupon_name == dop['name'] and coupon_title == dop['groupName']:
            print('Ставка в купоне есть')
            result = self.checkInfoCupon()
            print(result)
            return result
        else:
            print('Ставка в купоне не обнаружена')
            return False

    def checkInfoCupon(self) -> dict or bool:  # +
        '''собираем данные у купона'''
        # открываем купон
        if not self.check_open_coupone():
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
        coupon_btns = self.driver.find_elements_by_xpath(
            "//*[contains(@class, '__app-Tabs-tab')]/div")
        for btn in coupon_btns:
            if btn.get_attribute('innerText') == 'КУПОН ПАРИ':
                btn.click()
        replaced = {
            'max_limit': None,
            'min_limit': None,
            'current_odd': None
        }
        # max_limit, min_limit, current_odd = None, None, None
        for _ in range(3):  # 3 попытки получить данные
            try:
                amount_field = self.driver.find_element_by_xpath(
                    "//input[contains(@class, '__app-DropDown-input')]")
                amount_field.send_keys('10000000')
                self.check_loaded_page()
                # максимальная сумма ставки
                max_limit = amount_field.get_attribute('value')
                self.driver.implicitly_wait(3)
                amount_field.send_keys(Keys.CONTROL + 'a')
                amount_field.send_keys(Keys.BACKSPACE)
                time.sleep(1)
                amount_field.send_keys('1')
                min_limit = self.driver.find_element_by_xpath(
                    "//*[contains(@class, '__app-Error-container')]").get_attribute('innerText').split(':')[-1].strip()
                amount_field.send_keys(Keys.CONTROL + 'a')
                amount_field.send_keys(Keys.BACKSPACE)
                time.sleep(1)
                if amount_field.get_attribute('value') == '':
                    print('Поле ставки очищено')
                else:
                    amount_field.send_keys(Keys.CONTROL + 'a')
                    amount_field.send_keys(Keys.BACKSPACE)
                    time.sleep(1)
                # текущий коэффициент
                current_odd = self.driver.find_element_by_xpath(
                    "//*[contains(@class, 'app-OddValue-container')]").get_attribute('innerText')
            except Exception:
                print('Проверьте наличие купона на ставку')
            # если макс ставка 0 - значит ставку сделать нельзя
            if max_limit == '0':
                time.sleep(1)
                continue  # еще попытку сделаем
            else:
                replaced = {'max': max_limit,
                            'min': min_limit, 'koef': current_odd}
                return replaced
        return False

    def enter_cupon(self, price) -> bool:  # +
        '''проставляем сумму ставки в купоне'''
        self.check_loaded_page()
        # открываем купон
        if not self.check_open_coupone():
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
        coupon_btns = self.driver.find_elements_by_xpath(
            "//*[contains(@class, '__app-Tabs-tab')]/div")
        for btn in coupon_btns:
            if btn.get_attribute('innerText') == 'КУПОН ПАРИ':
                btn.click()
        try:
            price = str(price)
            self.driver.implicitly_wait(3)
            price_field = self.driver.find_element_by_xpath(
                "//input[contains(@class, '__app-DropDown-input')]")
            time.sleep(1)
            price_field.clear()
            price_field.send_keys(price)
            if price_field.get_attribute('value') == price:
                print(f'Ставка {price} поставлена в поле')
                return True
            else:
                print('Ставка не поставлена')
                return False
        except Exception as err:
            print('enter_cupon ', err, type(err))
            print(
                'Поставить такую ставку нельзя, возможно такой ставки уже не существует')
            return False

    def check_open_coupone(self) -> bool:  # +
        '''проверка открыт ли купон'''
        try:
            self.driver.find_element_by_xpath(
                "//*[contains(@class, 'is-open-sidebar')]")
            return True
        except NoSuchElementException:
            return False

    def paramStavka(self) -> str:  # +
        """возвращает значение param из self.dop"""
        for key, value in self.dop.items():
            return value.get('param')

    def to_cupon(self) -> dict:  # +
        """Нажимаем кнопку СДЕЛАТЬ СТАВКУ
        :return: Словарь со статусом и временем, за сколько принялась ставка (количество секунд). Пример:
            {'st': True, 'time': 2}
        """
        output = {'st': False, 'time': ''}
        try:
            button_bet = self.driver.find_element_by_xpath(
                "//*[contains(@class, 'placeBet__container')]")
            button_bet.click()  # поставили ставку
            # ставка ставится во вкладке КУПОН ПАРИ и Купон сразу закрывается
            start_time = time.time()
            # self.driver.refresh()
            # открываем купон
            if not self.check_open_coupone():
                WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                    (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
            coupon_btns = self.driver.find_elements_by_xpath(
                "//*[contains(@class, '__app-Tabs-tab')]/div")
            # переходим в МОИ ПАРИ
            for btn in coupon_btns:
                if btn.get_attribute('innerText') == 'МОИ ПАРИ':
                    btn.click()
            # переходим во вкладку Нерасчитанные
            WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(
                (By.XPATH, "//div[@data-tab='unsettled']"))).click()
            wait = WebDriverWait(self.driver, 20)
            xpath_selector = "//*[contains(@class, 'bet__container')]"
            try:
                wait.until(EC.visibility_of_element_located(
                    (By.XPATH, xpath_selector)))
                output = {'st': True, 'time': round(
                    time.time() - start_time, 2)}
                print('Ваша ставка успешно принята!')
            except Exception:
                print('Время принятия ставки больше 20 сек!')
                output = {'st': True, 'time': round(
                    time.time() - start_time, 2)}
            print('to_cupon output ', output)
            return output
        except Exception:
            print('Кнопка ставки неактивна')
            return output

    def addSettingsCupon(self, bk_setting: str) -> bool:  # +
        """ меняем настройки купона. Возможные
        Настройки уведомлений об изменении купона:
        не принимать no_koef/только лучшие up_koef/любые all_koef
        :param setting: no_koef, up_koef, all_koef
        :return: True - при удачной смене
        """
        if not self.check_open_coupone():
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
        coupon_btns = self.driver.find_elements_by_xpath(
            "//*[contains(@class, '__app-Tabs-tab')]/div")
        # print('всего кнопок в купоне ', len(coupon_btns))
        for btn in coupon_btns:
            if btn.get_attribute('innerText') == 'КУПОН ПАРИ':
                btn.click()
        self.driver.find_element_by_xpath(
            "//*[contains(@class, 'updatesSettings')]").click()
        self.check_loaded_page()
        setting_block = self.driver.find_elements_by_xpath(
            "//*[contains(@class, 'checkListItem__container')]")
        if setting_block:
            b_ever = setting_block[0]
            b_upper = setting_block[1]
            b_never = setting_block[2]
            if 'no_koef' in bk_setting:
                b_never.click()
                time.sleep(0.2)
                try:
                    b_never.get_attribute('checked')
                    print(
                        'Настройки изменены на Не принимать изменения коэффициентов'
                    )
                except Exception:
                    pass
            elif 'up_koef' in bk_setting:
                b_upper.click()
                # time.sleep(1)
                self.driver.implicitly_wait(2)
                try:
                    b_upper.get_attribute('checked')
                    print(
                        'Настройки изменены на Принимать только лучшие коэффициенты'
                    )
                except Exception:
                    pass
            elif 'all_koef' in bk_setting:
                b_ever.click()
                time.sleep(0.2)
                try:
                    b_ever.get_attribute('checked')
                    print(
                        'Настройки изменены на Принимать любые изменения коэффициентов'
                    )
                except Exception:
                    pass
            else:
                print(
                    'Настройки купона: Смена настроек коэффициентов не нужна'
                )
            return True
        else:
            print(
                'Настройки купона: Изменения коэффициентов не произошло. Проверьте входные данные'
            )
            return False

    def open_bets_history(self) -> bool:
        ''' открываем историю ставок - кнопка МОИ ПАРИ справа в углу'''
        history_url = 'https://ggbet.ru/live#!/player/profile-bets-history?_locale=ru'
        self.driver.find_element_by_xpath(
            "//*[contains(@class, 'auth-bar__btn--orange')]"
        ).click()
        if 'profile-bets-history' not in self.driver.current_url():
            self.driver.get(history_url)
        self.check_loaded_page()
        return True

    def checkInfoStavka(self, gameName) -> dict:  # +
        """
        Получаем информацию о ставке - из Мои Пари в Купоне
        :param gameName: имя Игры, типа "Игрок1 - Игрок 2"
        :return: {'koef': None, 'summ': None, 'game_name': None}
        """
        # открываем купон
        if not self.check_open_coupone():
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
        coupon_btns = self.driver.find_elements_by_xpath(
            "//*[contains(@class, '__app-Tabs-tab')]/div")
        # переходим в МОИ ПАРИ
        for btn in coupon_btns:
            if btn.get_attribute('innerText') == 'МОИ ПАРИ':
                btn.click()
        # переходим во вкладку Расчитанные
        WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@data-tab='settled']"))).click()
        time.sleep(1)
        all_bets = self.driver.find_elements_by_xpath(
            "//*[contains(@class, 'bet__container')]")
        output = {'koef': None, 'summ': None, 'game_name': None}
        for bet in all_bets:
            try:
                game_name = bet.find_element_by_xpath(
                    ".//*[contains(@class, 'sportEventInfo__body')]/a").get_attribute('innerText').strip()
                if game_name != gameName:
                    continue
                # game_id здесь не найти, будем юзать game_name
                game_koef = bet.find_element_by_xpath(
                    ".//*[contains(@class, 'odd__coef')]").get_attribute('innerText')  # коэф
                bet_summ = bet.find_elements_by_xpath(".//div[contains(@class, 'betFooter__value')]")[
                    0].get_attribute('innerText').replace('RUB', '').strip()
                # сумма ставки
                output = {
                    'koef': game_koef,
                    'summ': bet_summ,
                    'game_name': game_name
                }
                break
            except Exception as er:
                print(er, type(er))
                print('Ставка не найдена')
                print('Всего ставок в истории', len(all_bets))
                print('Искали', gameName)
        # закрываем купон
        self.driver.find_element_by_xpath(
            "//*[contains(@class, 'sidebarToggler__btn')]").click()
        print('=== checkInfoStavka ->', output)
        return output

    def statusVil(self, idGame) -> dict:  # +      idGame?
        """получаем статус ставки. статус ищем в Купоне->Мои Пари
        :param idGame: Словарь, где название игры - ключ, а параметр - id ставки.
            {'Команда 1 - Команда 2': '12345'}
            game_name ставки берем из: checkInfoStavka(gameName) -> get_id_bet(gameName)
        :return: [idGame[vil]] = {'status': 'lose', 'summ': '0'}
            status
            если Выиграл, то значение будет - {'status': 'win'}
            Проиграл - lose
            Возврат - return
            Продано - pay
        """
        output = {}
        # открываем купон
        if not self.check_open_coupone():
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
        coupon_btns = self.driver.find_elements_by_xpath(
            "//*[contains(@class, '__app-Tabs-tab')]/div")
        # переходим в МОИ ПАРИ
        for btn in coupon_btns:
            if btn.get_attribute('innerText') == 'МОИ ПАРИ':
                btn.click()
        # переходим во вкладку Расчитанные
        self.driver.find_element_by_xpath("//div[@data-tab='settled']").click()
        time.sleep(1)
        all_bets = self.driver.find_elements_by_xpath(
            "//*[contains(@class, 'bet__container')]")
        for bet in all_bets:
            # ищем совпадения по gameName
            game_name = bet.find_element_by_xpath(
                ".//*[contains(@class, 'sportEventInfo__body')]/a").get_attribute('innerText').strip()
            if game_name in list(idGame)[0]:
                # парсим сумму и результат ставки
                status = bet.find_elements_by_xpath(
                    ".//*[contains(@class, 'betFooter__title')]")[1].get_attribute('innerText').strip()
                # выплата
                payment = bet.find_elements_by_xpath(".//div[contains(@class, 'betFooter__value')]")[
                    1].get_attribute('innerText').replace('RUB', '').replace('+', '').replace('-', '').strip()
                # сумма ставки
                bet_summ = bet.find_elements_by_xpath(".//div[contains(@class, 'betFooter__value')]")[
                    0].get_attribute('innerText').replace('RUB', '').strip()
                bet_id = bet.find_element_by_xpath(
                    ".//*[contains(@class, 'betHeader__title')]").get_attribute('innerText')
                if "Проигрыш" in status:
                    output[bet_id] = {'status': 'lose', 'summ': bet_summ}
                elif 'Выигрыш' in status:
                    output[bet_id] = {'status': 'win', 'summ': bet_summ}
                if 'Продажа Ставки' in status:
                    output[bet_id] = {'status': 'pay', 'summ': payment}
                # это значение не проверялось!
                print('=== statusVil ->', output)
                return output
        raise Exception('Не удалось найти ставку', idGame)

    def autoSale(self, gameName, dop) -> dict or bool:  # +
        """Продаем ставку до срабатывания букмекеру.
        опция есть не на всех ставках, поймал на Тотал один раз!
        ориентируемся только на gameName
        :return: {'st': False, 'summ': None}
        """
        # output = {'st': None, 'summ': None}
        # открываем купон
        if not self.check_open_coupone():
            WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//*[contains(@class, 'sidebarToggler__btn')]"))).click()
        coupon_btns = self.driver.find_elements_by_xpath(
            "//*[contains(@class, '__app-Tabs-tab')]/div")
        # переходим в МОИ ПАРИ
        for btn in coupon_btns:
            if btn.get_attribute('innerText') == 'МОИ ПАРИ':
                btn.click()
        # переходим во вкладку Нерасчитанные
        WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@data-tab='unsettled']"))).click()
        try:
            # если есть кнопка Продажа Ставки
            bet_sale_btn = self.driver.find_element_by_xpath(
                "//*[contains(@class, 'toggler__button')]")
            bet_sale_amount = bet_sale_btn.get_attribute(
                'innerText').split('\n')[-1].replace('RUB', '')
            bet_sale_btn.click()
            time.sleep(1)
            # подтверждение продажи
            self.driver.find_elements_by_xpath(
                "//*[contains(@class, 'footer__accept')]").click()
            WebDriverWait(self.driver, 10).until(EC.visibility_of_element_located(
                (By.XPATH, "//*[contains(@class, 'success__bold')]")))
            # жмем на кнопку Ок
            self.driver.find_element_by_xpath(
                "//*[contains(@class, 'footer__ok')]").click()
            output = {'st': True, 'summ': bet_sale_amount}
            print('Ставка успешно продана!', output)
            return output
        except Exception:
            print('Опция Продажа Ставки отсутствует')
            return False


def main():
    obj = Ggbet(
        login=ggbet_settings.login,
        password=ggbet_settings.password,
        domain=ggbet_settings.domain
    )
    try:
        game_name = 'J&K Bank XI vs SCFA'
        dop = {
            "id": '8cb8df2b-f450-4523-9271-bc32fde01e66',
            "groupName": "Тотал",
            "name": "Under 4.5",
            "short_name": "Т_Under",
            "koef": '1.38',
            "param": "4.5"
        }
        # setting = 'up_koef'
        idGame = {'Ванкувер Кэнакс vs Seattle Kraken': '69557926'}
        obj.setup_method()
        print('драйвер запущен')
        obj.open_home_page()
        obj.auth()
        obj.enter_live()
        obj.get_balance()
        obj.openGameNew(game_name, dop)
        time.sleep(5)
        # print('открыли игру')
        obj.openCupon()
        time.sleep(5)
        # print('Выбрали ставку')
        obj.enter_cupon(price=50)
        time.sleep(5)
        # obj.to_cupon()
        # time.sleep(5)
        obj.autoSale(game_name, dop)
        # time.sleep(10)
        obj.clearCupon()
        # obj.checkInfoStavka('Сычуань Цзюню vs Beijing Technology')
        obj.statusVil(idGame)
    except Exception as err:
        print(err)
        print('not found')
    finally:
        time.sleep(10)
        obj.teardown_method()


if __name__ == '__main__':
    main()
