# -*- coding: utf-8 -*-
# !/usr/bin/env python3

import os
import re
import sys
import time
import json
import urllib
import random
import pickle
import requests
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

import leon_settings


class Leon:

    """Selenium bot for Leon RU"""

    def __init__(self, login, password, domain):
        # self.login = client_id
        self.login = login  # email
        self.password = password
        self.domain = domain

    def setup_method(self):
        ''' инициализация драйвера '''
        # убираем детект Селениума
        options = webdriver.ChromeOptions()
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        # убирает "Браузером управляет Тестовое ПО"
        options.add_experimental_option(
            "excludeSwitches",
            ["enable-automation"]
        )
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
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.vars = {}

    def teardown_method(self):
        ''' закрытие браузера '''
        self.driver.close()
        self.driver.quit()

    def check_loaded_page(self) -> bool:
        """при открытии страниц сайта ждем полной загрузки"""
        WebDriverWait(self.driver, 10).until(lambda driver: self.driver.execute_script(
            'return document.readyState') == 'complete')
        return True

    def open_home_page(self) -> bool:
        '''открываем главную страницу'''
        self.driver.get(self.domain)
        return True

    def auth(self) -> bool:
        ''' авторизация, True/False '''
        self.check_loaded_page()
        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@class, 'button--login')]"))).click()
        self.check_loaded_page()
        # переключаемся на модальное окно
        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(@class, 'tab-EMAIL')]"))).click()
        # self.driver.find_element_by_xpath("//button[contains(@class, 'tab-EMAIL')]").click()
        self.driver.find_element(
            By.XPATH, "//input[contains(@id, 'login')]").send_keys(self.login)
        self.driver.find_element(
            By.XPATH, "//input[contains(@class, 'password')]").send_keys(self.password)
        self.driver.find_element(
            By.XPATH, "//button[contains(@class, 'button--kind-success')]").click()
        self.check_loaded_page()
        try:
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//*[@class='popover']")))
            print('Залогинились')
            return True
        except Exception:
            print('Аутентификация не удалась!')
            return False

    def get_balance(self) -> int or bool:
        '''получаем доступный баланс'''
        # проверка авторизации
        try:
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'button--login')]")))
            self.auth()
        except Exception:
            pass
        try:
            balance = self.driver.find_element(
                By.XPATH, "//div[@class='balance__info-text']").get_attribute('innerText').split()[0]
        except NoSuchElementException as err:
            print(err, 'Баланс не найден')
            balance = False
        self.balance = balance
        print('Текущий баланс', balance)
        return balance

    def enter_live(self) -> bool:
        ''' заходим в лайв игры '''
        self.driver.find_element(
            By.XPATH, "//a[contains(@class, 'top-sportline-live-events')]").click()
        self.check_loaded_page()
        self.driver.implicitly_wait(7)
        try:
            self.driver.current_url == 'https://leon.ru/live'
            print('Зашли в live')
            return True
        except Exception:
            print('Страница не live!')
            return False

    def openGameNew(self, game_name: str, dop: dict, ligaName='') -> bool:
        '''заходим на страницу выбранной игры'''
        # проверим, что находимся в лайве
        try:
            self.driver.current_url == 'https://leon.ru/live'
        except Exception:
            self.enter_live()
        # все доступные игры в лайве
        games = self.driver.find_elements(
            By.XPATH, "//*[contains(@class, 'sport-event-list-item--live')]")
        print(len(games), 'игр всего сейчас в лайв')
        # gamer_arr = {}
        print("Ищем игру", game_name)
        for game in games:
            g_name = game.find_element(
                By.XPATH, ".//*[contains(@class, 'sport-event-list-item-scoreboard__left-column')]").get_attribute('innerText').replace('\n', ' - ')
            # "Аль-Хидд\nМанама"  ->  "Аль-Хидд - Манама"
            if game_name != g_name:
                continue
            game_url = game.find_element(
                By.XPATH, ".//*[contains(@class, 'sport-event-list-item__competitors')]").get_attribute('href')
            game.find_element(
                By.XPATH, ".//*[contains(@class, 'sport-event-list-item__competitors')]").click()
            break
        # проверка правильности открытой игры
        try:
            game_url == self.driver.current_url
            self.dop = dop
            print('Игра открыта правильно')
            return True
        except Exception:
            print('Игра не найдена')
            return False

    def clearCupon(self) -> bool:
        ''' очистка купона от всех выбранных коэффициентов '''
        # в купоне жмем кнопку Купон
        self.driver.find_element(
            By.XPATH, "//button[@data-test-id='tab-slip']").click()
        try:
            btn_remove = self.driver.find_element(
                By.XPATH, "//button[@class='bet-slip-event-card__remove']")
            btn_remove.find_element(
                By.XPATH, ".//*[name()='use' and @*[contains(., '#icon-cross-padded-usage')]]").click()
        except NoSuchElementException:
            print('Кнопка очистки купона не найдена')
        # проверка очистки купона
        try:
            self.driver.find_element(
                By.XPATH, "//h4").get_attribute('innerText') == "КУПОН ПУСТ"
            print("Купон пуст")
            return True
        except NoSuchElementException:
            print('Проверьте очистку купона!')
            return False

    def addSettingsCupon(self, bk_setting: str) -> bool:
        """ меняем настройки купона.
            Возможные настройки:
            Автоподтверждение коэффициентов откл (no_koef) ->
            Изменения только вверх   up_koef
            Любые изменения(вверх и вниз)   all_koef
        :param setting: no_koef, up_koef, all_koef
        :return: True - при удачной смене
        """
        # в купоне жмем кнопку Купон
        self.driver.find_element(
            By.XPATH, "//button[@data-test-id='tab-slip']").click()
        # открываем настройки купона
        self.driver.find_element(
            By.XPATH, "//*[contains(@class, 'button--width-fixed-middle')]").click()
        try:
            if bk_setting == 'no_koef':
                try:
                    self.driver.find_element(
                        By.XPATH, "//*[@class='auto-update__options']")
                    self.driver.find_element(
                        By.XPATH, "//*[@class='switch__switcher']").click()
                except Exception:
                    pass
                print('Автоподтверждение коэффициентов отключено')
            else:
                try:
                    self.driver.find_element(
                        By.XPATH, "//*[@class='auto-update__options']")
                except Exception:
                    self.driver.find_element(
                        By.XPATH, "//*[@class='switch__switcher']").click()
                self.check_loaded_page()
                btn_up = self.driver.find_elements(
                    By.XPATH, "//li[@class='auto-update__option']")[0]
                btn_all = self.driver.find_elements(
                    By.XPATH, "//li[@class='auto-update__option']")[-1]
                if (bk_setting == 'up_koef'):
                    btn_up.find_element(
                        By.XPATH, ".//span[@class='radio__icon']").click()
                    if 'radio--checked' in btn_up.find_element(By.XPATH, "./label").get_attribute('className'):
                        print(
                            'Настройка Автоподтверждение коэффициентов - Изменения только вверх принята')
                    else:
                        print(
                            'Настройка Автоподтверждение коэффициентов - Изменения только вверх НЕ ПРИНЯТА!')
                elif (bk_setting == 'all_koef'):
                    btn_all.find_element(
                        By.XPATH, ".//span[@class='radio__icon']").click()
                    if 'radio--checked' in btn_all.find_element(By.XPATH, "./label").get_attribute('className'):
                        print(
                            'Настройка Автоподтверждение коэффициентов - Любые изменения принята')
                    else:
                        print(
                            'Настройка Автоподтверждение коэффициентов - Любые изменения НЕ ПРИНЯТА!')
            # закрываем настройки купона
            self.driver.find_element(
                By.XPATH, "//*[@data-test-id='settings-back']").click()
            try:
                self.driver.find_element(
                    By.XPATH, "//*[@data-test-id='settings-button']")
                print('Настройки купона успешно скрыты')
                return True
            except Exception:
                print('Настройки купона НЕ ЗАКРЫТЫ!')
                return False
        except Exception as er:
            print('Проверьте входные данные', er, type(er))
            return False

    def openCupon(self, bk_setting, max_error=3) -> dict or bool:
        '''
        выбор нужной ставки на странице игры,
        данные берутся из self.dop
        {'id': 1970324839304362,
        'groupName': 'Азиатский тотал',
        'name': 'Меньше (1.75)',
        'short_name': 'Т_М(1.75)',
        'koef': '2.95',
        'param': '1.75'}
        '''
        self.clearCupon()  # очищаем купон
        dop = self.dop
        # меняем настройки купона
        self.addSettingsCupon(bk_setting)
        # проверка доступности ставок
        try:
            self.driver.find_element(
                By.XPATH, "//div[@class='hint-block__labels']")
            print("Прием ставок на это событие приостановлен")
            print("Ждем открытия маркетов в течении 5 минут")
            # ждем 5 мин, пока этот элемент исчезнет
            WebDriverWait(self.driver, 300).until(EC.invisibility_of_element_located(
                (By.XPATH, "//div[@class='hint-block__labels']")))
        except TimeoutException:
            print('Время ожидания открытия маркетов больше 5 минут!')
            print('Выберите другое событие, чтобы сделать ставку')
            return False
        except Exception:
            print('Ставки доступны')
        # жмем на кнопку Все, чтобы открыть все ставки
        WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "//*[contains(@class, 'tab-tabAll')]"))).click()
        # ждем появления хотя бы одного блока со ставками
        WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "//*[contains(@class, 'sport-event-details__market') and not(contains(@class, 'hidden'))]")))
        # находим все блоки со ставками
        blocks = self.driver.find_elements(
            By.XPATH, "//*[contains(@class, 'sport-event-details__market')]")
        for block in blocks:
            group_name = block.find_element(
                By.XPATH, ".//div[@class='sport-event-details-item__title']").get_attribute('innerText')
            if dop['groupName'] != group_name:
                continue
            bets = block.find_elements(
                By.XPATH, ".//div[@class='sport-event-details-item__runner']")
            for bet in bets:
                bet_name = bet.find_elements(
                    By.XPATH, ".//span")[0].get_attribute('innerText')
                if bet_name != dop['name']:
                    continue
                bet_koef = bet.find_elements(
                    By.XPATH, ".//span")[-1].get_attribute('innerText')
                bet.click()
                break
            break
        # проверка появилась ли в купоне нужная ставка
        self.check_loaded_page()
        time.sleep(2)
        try:
            self.driver.find_element(
                By.XPATH, "//div[contains(@class, 'bet-slip-empty-placeholder')]")  # купон пуст
            print(
                "Такой ставки или уже не существует, или поменялся коэффициент, проверьте купон!")
            return False
        except Exception:
            pass
        try:
            bet_info = self.driver.find_element(
                By.XPATH, "//*[@class='bet-slip-event-card__prediction']").get_attribute('innerText')
            bet_info in dop['groupName'] and bet_info in dop['name']
            print("Нужная ставка ожидает в купоне")
            result = self.checkInfoCupon()
            print(result)
            return result
        except Exception:
            print("Проверьте ставку в купоне")
            return False

    def check_availability_of_bet(self) -> bool:
        '''
        проверка доступности ставок на событие
        работает только если в купоне выбрана ставка
        '''
        try:
            blocked_msg = self.driver.find_element(
                By.XPATH, "//*[@data-test-id='blocked-message']")
            try:
                'display: none;' in blocked_msg.get_attribute('style')
                print('Купон открыт для ставок')
                return True
            except Exception:
                print('Купон закрыт для ставок!')
                return False
        except NoSuchElementException:
            return False

    def checkInfoCupon(self) -> dict or bool:
        '''собираем данные у купона'''
        max_limit, min_limit, current_odd = None, None, None
        if not self.check_availability_of_bet():
            current_odd = self.driver.find_element(
                By.XPATH, "//*[@class='stake-input__value']").get_attribute('value')
            print('В данный момент получить данные купона невозможно!')
            return False
        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "stake-input__value"))).click()
        # time.sleep(3)
        for _ in range(5):  # 5 попыток получить данные
            try:
                bet_info = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(
                    (By.XPATH, "//div[@class='bet-slip-summary__error-label']"))).get_attribute('innerText')
                # print('InfoCupon bet_info', bet_info)
                # "от 20 ₽ до 279 751.50 ₽"
                min_limit, max_limit = bet_info.split('₽')[:-1]
                min_limit = min_limit.split('от')[-1].strip()
                max_limit = max_limit.split(
                    'до')[-1].strip().replace('\xa0', '')
                current_odd = self.driver.find_element(
                    By.XPATH, "//*[@class='stake-input__value']").get_attribute('value')
            except Exception:
                print('Не удалось получить данные по купону')
                continue
            break
        replaced = {'max_limit': max_limit,
                    'min_limit': min_limit, 'current_odd': current_odd}
        return replaced

    def enter_cupon(self, price) -> bool:
        '''проставляем сумму ставки в купоне'''
        price = str(price)
        # проверка доступности ставок на это событие
        if not self.check_availability_of_bet():
            print('В данный момент Недоступно для ставок')
            return False
        try:
            amount_field = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CLASS_NAME, "stake-input__value")
                )
            )
            amount_field.send_keys(Keys.CONTROL + 'a')
            amount_field.send_keys(Keys.BACKSPACE)
            amount_field.send_keys(price)
            # time.sleep(5)
        except Exception as er:
            print('enter_cupon -> ', er, type(er))
        try:
            self.driver.find_element(
                By.XPATH, "//*[@class='stake-input__value']").get_attribute('value') == price
            print(f'Ставка {price} проставлена в поле купона')
            # time.sleep(5)
            return True
        except Exception:
            print('Ошибка при проставлении суммы ставки!')
            return False

    def paramStavka(self) -> str:
        """возвращает значение param из self.dop"""
        for key, value in self.dop.items():
            return value.get('param')

    def to_cupon(self) -> dict:
        """Нажимаем кнопку СДЕЛАТЬ СТАВКУ
        :return: Словарь со статусом и временем, за сколько принялась ставка (количество секунд). Пример:
            {'st': True, 'time': 2}
        """
        output = {'st': False, 'time': ''}
        try:
            # жмем сделать ставку
            self.driver.find_element(
                By.XPATH, "//*[contains(@class, 'button--radius-square')]").click()
            start_time = time.time()
            # ориентируемся на кнопку Готово
            xpath_selector = "//*[contains(@class, 'button--height-small LoadingButton_loading-button_x2wrQ undefined')]"

            try:
                WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, xpath_selector)))
                print('Ваша ставка успешно принята!')
                output = {
                    'st': True, 'time': round(time.time() - start_time, 2)}
                # жмем кнопку Готово
                self.driver.find_element(By.XPATH, xpath_selector).click()
            except Exception as er:
                try:
                    # если доступна кнопка Готово - ставка принята
                    WebDriverWait(self.driver, 20).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_selector))).click()
                    output = {
                        'st': True, 'time': round(time.time() - start_time, 2)}
                except Exception:
                    # если доступна кнопка Закрыть - ставка не принята
                    self.driver.find_element(By.XPATH, "//*[contains(@class, 'bet-slip-result__heading')]").get_attribute(
                        'innerText') == "НЕ УДАЛОСЬ ПРИНЯТЬ ВАШУ СТАВКУ"
                    print('Не удалось принять вашу ставку!')
                    self.driver.find_element(
                        By.XPATH, "//*[contains(@class, 'LoadingButton_loading-button_x2wrQ')]").click()
                    output = {
                        'st': False, 'time': round(time.time() - start_time, 2)}
                print(f'{er} Время принятия ставки больше 20 сек!')
            print('to_cupon output ', output)
            return output
        except Exception:
            print('Кнопка ставки неактивна')
            return output

    def checkInfoStavka(self, gameName) -> dict:
        """
        Получаем информацию о ставке - из Истории транзакций
        :param gameName: имя Игры, типа "Игрок1 - Игрок 2"
        :return: {'koef': None, 'summ': None, 'id': None}
        """
        koef, payment, g_name = None, None, None
        output = {'koef': koef, 'summ': payment, 'game_name': g_name}
        # в купоне жмем Мои ставки
        self.driver.find_element(
            By.XPATH, "//*[@data-test-id='tab-my-bets']").click()
        # жмем Вся история ставок
        self.driver.find_element(
            By.XPATH, "//*[@class='bet-slip-my-bets__details-link']").click()
        # открывается новая страница История транзакций - Ставки
        # жмем в Истории транзакций кнопку Все
        self.driver.find_element(
            By.XPATH, "//*[@class='swiper__items']//li[1]/button").click()
        # вся таблица со ставками
        table = self.driver.find_element(
            By.XPATH, "//*[@class='history-list--desktop']/tbody")
        trs = table.find_elements_by_xpath(".//tr")
        for tr in trs:
            g_name = tr.find_elements(
                By.XPATH, ".//*[@class='text']")[0].get_attribute('innerText')
            if g_name != gameName:
                continue
            koef = tr.find_element(
                By.XPATH, ".//*[@data-test-key='odds']").get_attribute('innerText')
            # сколько выплачено по ставке, если + выиграло или возврат
            try:
                payment = tr.find_element(
                    By.XPATH, ".//*[@data-test-key='credit']").get_attribute("innerText").split()[0]
            except Exception:
                payment = ''  # если ставка еще не сыграла
            output = {'koef': koef, 'summ': payment, 'game_name': g_name}
            print(' checkInfoStavka ->', output)
            self.enter_live()  # возвращаемся в лайв
            return output
        raise Exception('Не удалось найти ставку', gameName)

    def autoSale(self, gameName, dop, idVil=None) -> dict:
        """
        Продаем ставку до срабатывания букмекеру.
        ориентируемся только на gameName
        idVil = 0 - продажа по gameName
        idVil != 0 - продажа по id
        :return: {'st': False, 'summ': None}
        """
        status, payment = None, None
        output = {'st': status, 'summ': payment}
        dop = self.dop
        if idVil is None:
            idVil = 0
        # в купоне жмем Мои ставки
        self.driver.find_element(
            By.XPATH, "//*[@data-test-id='tab-my-bets']").click()
        # проверка нужной ставки
        try:
            # если ставка есть
            bet_info = self.driver.find_element(
                By.XPATH, "//*[contains(@class, 'bet-slip-event-card__column--left')]")
        except Exception:
            print("Ставки в купоне не обнаружено!")
            return output
        try:
            if idVil:
                pass
            else:
                gameName in bet_info.get_attribute('innerText')
        except Exception:
            print('Ставка в купоне откличается от нужной!')
            return output
        # жмем на ставку в купоне
        bet_info.click()
        # определяем модальное окно
        modal = self.driver.find_element(
            By.XPATH, "//div[@class='modal__inner']")
        btn_selector = (
            ".//*[contains(@class, 'button button--kind-success')]")
        print('Ищем кнопку продажи ставки...')
        try:
            # ждем появления кнопки Продать ставку 5 минут
            WebDriverWait(modal, 300).until(
                EC.element_to_be_clickable((By.XPATH, btn_selector))).click()
            print('Начало продажи ставки...')
            try:
                # если сумма поменялась - появляется такая же кнопка, жмем
                modal.find_element(By.XPATH, btn_selector).click()
            except Exception:
                pass
            # в конце появляется текст СТАВКА ПРОДАНА, а на кнопке ГОТОВО
            payment = modal.find_elements(
                By.XPATH, ".//ul//li")[-1].get_attribute('innerText').split('\n')[-1].split()[0]
            print('payment', payment)
            status = modal.find_elements(
                By.XPATH, ".//ul//li")[1].get_attribute('innerText').split('\n')[-1]
            try:
                'Продан' in status
                print('Ставка успешно продана!')
            except Exception:
                print('Неудачная продажа ставки')
            try:
                # жмем кнопку Готово, если она еще не нажата
                modal.find_element(By.XPATH, btn_selector).click()
                print('Нажали кнопку ГОТОВО')
            except Exception:
                pass
        except TimeoutException:
            # если кнопка не появилась в течении 5 мин
            print('Время продажи больше 5 минут!')
        # закрываем модальное окно
        self.driver.find_element(
            By.XPATH, "//*[contains(@class, 'desktop-modal-top-bar__cross')]").click()
        self.enter_live()  # возвращаемся в лайв
        print('autoSale output ->', output)
        return output

    def statusVil(self, idGame) -> dict:
        """получаем статус ставки. статус ищем на странице с историей ставок
        :param idGame: Словарь, где название игры - ключ, а параметр - id ставки.
            {'Команда 1 - Команда 2': '12345'}
            id ставки берем из: checkInfoStavka(gameName) -> get_id_bet(gameName)
        :return: [idGame[vil]] = {'status': 'lose', 'summ': '0'}
            status
            если Выиграл, то значение будет - {'status': 'win'}
            Проиграл - lose
            Возврат - return
            Продано - pay
        """
        output = {}
        # в купоне жмем Мои ставки
        self.driver.find_element(
            By.XPATH, "//*[@data-test-id='tab-my-bets']").click()
        # жмем Вся история ставок
        self.driver.find_element(
            By.XPATH, "//*[@class='bet-slip-my-bets__details-link']").click()
        # открывается новая страница История транзакций - Ставки
        # жмем в Истории транзакций кнопку Все
        self.driver.find_element(
            By.XPATH, "//*[@class='swiper__items']//li[1]/button").click()
        # вся таблица со ставками
        table = self.driver.find_element(
            By.XPATH, "//*[@class='history-list--desktop']/tbody")
        trs = table.find_elements(By.XPATH, ".//tr")
        for tr in trs:
            bet_id = ''
            g_name = tr.find_elements(
                By.XPATH, ".//*[@class='text']")[0].get_attribute('innerText')
            if g_name != list(idGame)[0]:
                continue
            # жмем на ставку в купоне
            tr.click()
            # time.sleep(1)
            # модальное окно
            modal = self.driver.find_element(
                By.XPATH, "//div[@class='modal__inner']")
            bet_id = modal.find_element(
                By.XPATH, ".//div[@class='transaction-details__number']").get_attribute('innerText')
            lis = modal.find_elements(By.XPATH, ".//ul//li")
            for li in lis:
                row = li.get_attribute('innerText')
                if 'Выигрыш:' in row:
                    payment = row.split('\n')[-1].split()[0]
                elif 'Коэффициент:' in row:
                    koef = row.split('\n')[-1]
                elif 'Статус:' in row:
                    status = row.split('\n')[-1]
                elif 'Сумма ставки:' in row:
                    amount = row.split('\n')[-1].split()[0]
            if "Проигран" in payment:
                output[bet_id] = {'status': 'lose', 'summ': amount}
            elif 'Продан' in status:
                output[bet_id] = {'status': 'pay', 'summ': payment}
            elif 'Разыгран' in status:
                if koef == '1.00':
                    output[bet_id] = {'status': 'return', 'summ': payment}
                else:
                    output[bet_id] = {'status': 'win', 'summ': payment}
            print(' statusVil ->', output)
            # закрываем модальное окно
            self.driver.find_element(
                By.XPATH, "//*[contains(@class, 'desktop-modal-top-bar__cross')]").click()
            self.enter_live()  # возвращаемся в лайв
            return output
        raise Exception('Не удалось найти ставку', idGame)


def main():
    obj = Leon(
        login=leon_settings.login,
        password=leon_settings.password,
        domain=leon_settings.domain
    )
    try:
        game_name = 'Вегас Голден Найтс - Калгари Флэймз'
        dop = {"id": '1970324839304098',
               "groupName": "Тотал хозяев",
               "name": "Больше (1.5)",
               "short_name": "Т_Under",
               "koef": '1.30',
               "param": "4.5"}
        bk_setting = 'up_koef'
        obj.setup_method()
        print('драйвер запущен')
        obj.open_home_page()
        obj.auth()
        obj.enter_live()
        obj.get_balance()
        obj.addSettingsCupon(bk_setting)
        obj.openGameNew(game_name, dop)
        # time.sleep(5)
        obj.openCupon(bk_setting)
        # time.sleep(5)
        obj.enter_cupon(price=20)
        # time.sleep(5)
        obj.to_cupon()
        # time.sleep(5)
        obj.clearCupon()
    except Exception as err:
        print(err, type(err))
        print(' === main error === ')
    finally:
        time.sleep(10)
        obj.teardown_method()


if __name__ == '__main__':
    main()
