from playwright.sync_api import sync_playwright, TimeoutError, Error, expect
from fake_useragent import UserAgent
from pathlib import Path
from datetime import datetime
from ctypes import wintypes, windll, create_unicode_buffer, byref
import keyboard
import winreg
import model
import config
import time
import service


# словарь-соответствие между обозначанием типа ответов на странице и в БД questionType
MATCHING_QUESTION_TYPES = {
    'Одиночный выбор • с выбором одного правильного ответа из нескольких предложенных вариантов': 'choice',
    'Множественный выбор • с выбором нескольких правильных ответов из предложенных вариантов': 'choiceMultiple',
    'Текcтовый ответ': 'textEntry',
    'Сортировка': 'order',
    'Сопоставление': 'match',
}


# question_block_id - определяется в первом запросе ответа и сохраняется на время текущего теста
# count_unfound_answers - число не найденных овтетов в текущем тесте
# complete_test - признак что достигнут конец тестовых вопросов
# __manual_presskey - если True, то парсер перестает сам нажимать на кнопку отправки ответа или пропуска
class SynergyParser:
    def __init__(self, start_url: str) -> None:
        self.start_url = start_url
        self.ua = UserAgent()
        self.__settings = self.__load_settings()
        self.proxy_info = self.__get_unused_proxy()
        self.__playwright = sync_playwright().start()
        self.__browser = self.__playwright.chromium.launch(headless=False,
                                                           args=[
                                                               '--start-maximized'],
                                                           ignore_default_args=[
                                                               '--enable-automation'],
                                                           proxy=self.__get_proxy_settings())
        self.__context = self.__browser.new_context(user_agent=self.ua.random,
                                                    no_viewport=True)
        self.__context.grant_permissions(permissions=['camera'])
        self.page = self.__context.new_page()
        self.page.add_init_script("""
                                  Object.defineProperty(navigator, "webdriver", {get: () => undefined,});
                                  """)
        self.__matching_question_types = MATCHING_QUESTION_TYPES
        self.__test_info = {}
        self.__question_block_id = 0
        self.__count_unfound_answers = 0
        self.__path_log_file = ''
        self.__complete_test = False
        self.__manual_presskey = False
        self.__pid = self.__get_active_window_pid()
        self.__set_used_proxy()
        self.__set_hotkey()
        self.__begin_autotest_running = False

    def __set_hotkey(self) -> None:
        if self.__settings.get('use_hotkey', 0):
            keyboard.add_hotkey(
                'ctrl+F4', self.__set_manual_presskey, suppress=True)

    def __set_manual_presskey(self) -> None:
        active_pid = self.__get_active_window_pid()

        if self.__pid == active_pid:
            self.__manual_presskey = not self.__manual_presskey

    def __get_active_window_pid(self) -> int:
        pid = wintypes.DWORD()
        active_hwnd = windll.user32.GetForegroundWindow()
        active_window_pid = windll.user32.GetWindowThreadProcessId(
            active_hwnd, byref(pid))
        return active_window_pid

    # не используется, получает имя активного окна
    def __get_foreground_window_title(self) -> str:
        active_hwnd = windll.user32.GetForegroundWindow()
        length = windll.user32.GetWindowTextLengthW(active_hwnd)
        buf = create_unicode_buffer(length + 1)
        windll.user32.GetWindowTextW(active_hwnd, buf, length + 1)
        return buf.value if buf.value else ''

    def get_access(self) -> bool:
        result = False

        try:
            with winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, 'Software\SFS') as key:
                value, type_value = winreg.QueryValueEx(key, 'SFS_key')
                result = (value == config.KEY_ACCESS_VALUE)
        except FileNotFoundError:
            if config.DEBUG:
                print('Не найден ключ защиты')

        return result

    # ********************* Работа с прокси ******************************************************************************
    # Пример результата: proxy={"server": "http://83.167.122.108:1405", "username": "em7YT4", "password": "AzRAB9uc2ukp"})
    def __get_proxy_settings(self) -> dict | None:
        proxy = {}

        if not self.proxy_info:
            return None

        proxy['server'] = f'http://{self.proxy_info["ip"]}:{self.proxy_info["port"]}'
        proxy['username'] = self.proxy_info['user']
        proxy['password'] = self.proxy_info['password']

        return proxy

    def __get_unused_proxy(self) -> dict:
        proxy_info = {}

        if not self.__settings.get('use_proxy', 0):
            return proxy_info

        proxy_info = model.get_unused_proxy()
        return proxy_info

    # если используем прокси, то в БД укажем что используем его
    def __set_used_proxy(self) -> None:
        if self.__settings.get('use_proxy', 0):
            model.set_proxy_used(self.proxy_info.get('ip', ''))

    def __free_used_proxy(self) -> None:
        if self.__settings.get('use_proxy', 0):
            model.free_proxy_used(self.proxy_info.get('ip', ''))

    # Проверяет включено ли использование прокси и есть ли при этом свободный прокси в БД, иначе завершает программу
    def __check_free_proxy(self) -> None:
        if self.__settings.get('use_proxy', 0) and not self.proxy_info:
            self.page.wait_for_timeout(2000)
            self.__alert('Нет свободных прокси!')
            self.stop()

    # ******************* Конец работы с прокси ************************************************************

    def __load_settings(self) -> dict:
        settings = {}

        with open('settings.cfg', 'r', encoding='utf-8') as f:
            for line in f:
                if '#' in line or '=' not in line:
                    continue

                data_setting = line.split('=')
                parameter = data_setting[0].strip()
                value = data_setting[1].strip()

                if value.isdecimal():
                    value = int(value)
                else:
                    self.__logging(
                        'Ошибка загрузки настроек: параметр должен быть целым числом')

                settings[parameter] = value

        return settings

    # ЧАСТЬ ДЛЯ РУЧНОГО ПОИСКА И ЗАПУСКА ТЕСТА **************************************************************************************************************************
    # стартует программа без логина студента, но с ожиданием появления таймера (#testTimeLimit) теста на странице и если он есть, то запускает автотест (ожидает однократно)
    def start_manually(self) -> None:
        self.page.goto(self.start_url)

        self.page.on('dialog', lambda dialog: print(
            f'{dialog.message}') if config.DEBUG else ...)
        self.__check_free_proxy()

        try:
            self.page.on('load', self.__check_begin_test)
        except TimeoutError:
            pass
        except Error:
            pass
        finally:
            self.__pause()

    # Добавляет JS скрипты на страницу для изменения ссылок(убираю атрибут terget что бы ссылки открывались только в текущей вкладке)
    # и для предотвращения замедления страницы в фоновом режиме
    def __add_scripts_on_page(self) -> None:
        if self.proxy_info:
            self.page.evaluate(
                f'document.querySelector("title").textContent = "{self.proxy_info.get("ip", "0.0.0.0")}";')

        self.page.evaluate(
            '() => { let elements = document.querySelectorAll("a"); for (let elem of elements) { elem.removeAttribute("target"); } }')

        self.page.evaluate("""
            { let lastTime = performance.now();
            (function loop() {
                let f = 1000 / (performance.now() - lastTime) | 0;
                lastTime = performance.now();
                setTimeout(loop, 10);
            })(); }
            """)

    # поиск признака начала теста
    def __check_begin_test(self) -> None:
        try:
            if self.page.locator('#popupUsername').count() > 0:
                return
        except Error:
            pass

        if config.DEBUG:
            print('Ищем таймер теста...')

        error_msg = self.__find_server_errors()

        if error_msg:
            self.__reload(error_msg)
            return

        self.__add_scripts_on_page()

        try:
            # Если нашли кнопку идентификации теста, значит мы начинаем новый тест и нужно сбросить старые значения объекта парсера
            # не зависимо завершили мы прошлый тест или нет
            if self.page.locator('#cvsBtn').count() > 0:
                self.__test_info = {}
                self.__question_block_id = 0
                self.__count_unfound_answers = 0
                self.__path_log_file = ''

                if config.DEBUG:
                    print('Обнаружена кнопка идентификации начала теста!')
        except Error:
            pass

        try:
            # Если таймер обнаружен и self.__begin_autotest() еще не запущена, то запустим ее
            self.__wait_finish_begin_autotest()

            if self.page.locator('#testTimeLimit').count() > 0 and not self.__begin_autotest_running:
                error_msg = self.__begin_autotest()
                self.__begin_autotest_running = False

                if config.DEBUG:
                    print('ВЕРНУЛИСЬ ИЗ __begin_autotest')
        except TimeoutError:
            error_msg = 'Не обнаружен таймер теста ...'
        except Error:
            error_msg = 'Не обнаружен таймер теста ...'

        if error_msg:
            if config.DEBUG:
                print(error_msg)

            self.__reload(error_msg)

    # начинаем автотест на стандартной странице теста
    def __begin_autotest(self) -> str:
        error_msg = ''
        self.__begin_autotest_running = True

        if config.DEBUG:
            print('<<<<< Обнаружен вопрос >>>>>')

        # error_msg = self.__find_server_errors()

        # if error_msg:
        #     return error_msg

        if not self.__path_log_file:
            error_msg = self.__create_log_file()

        if error_msg:
            return error_msg

        self.__pause_for_answer()
        self.__test_info, error_msg = self.__get_test_info()

        if error_msg:
            return error_msg

        if self.__complete_test:
            finish, error_msg = self.__finish_test()
            return error_msg

        error_msg = self.__is_last_question()

        if error_msg:
            return error_msg

        if self.__need_skip_question():
            self.__pause_for_answer()
            error_msg = self.__skip_question('Искусственный пропуск вопроса')
            return error_msg

        variants_question, raw_text_question, error_msg = self.__get_question()

        if error_msg:
            return error_msg
        elif not variants_question:
            error_msg = 'Не удалось получить вопрос!'
            return error_msg
        
        if config.DEBUG:
            print(f'Поисковые фразы:\n{variants_question}')

        self.__logging(f'Вопрос: {raw_text_question}')
        type_question, error_msg = self.__get_question_type()

        if error_msg:
            return error_msg

        self.__logging(f'Тип вопроса: {type_question}')
        need_skip, need_reload, error_msg = self.__searching_for_answer(
            variants_question, type_question)

        if need_skip:
            self.__skip_question(error_msg)
            return ''
        elif need_reload:
            return error_msg

        self.__pause_for_answer()
        error_msg = self.__send_answer()

        if error_msg:
            # self.__reload(error_msg)
            return error_msg

    # Определяет возникновение ошибок на стороне сервера, как правило при этом футер не прогружен
    def __find_server_errors(self) -> str:
        error_msg = ''

        try:
            if self.page.locator('center.removeOnError').count() > 0:
                error_msg = 'Ошибка 502'
                return error_msg
        except Error:
            pass

        try:
            self.page.locator('#bottom-menu').wait_for()
        except TimeoutError:
            error_msg = 'Нет подвала на странице'
        except Error:
            error_msg = 'Нет подвала на странице'

        return error_msg
    

    # Ожидание окончания парарлельного запуска функции __begin_autotest
    def __wait_finish_begin_autotest(self) -> None:
        count = 0
        timeout = 10

        while self.__begin_autotest_running and count < timeout:
            time.sleep(1)
            count += 1

        if count == timeout:
            self.__logging(f'Не дождались завершения __begin_autotest за {timeout} сек')
            self.__begin_autotest_running = False


    # делает паузу между ответами, если пауза меньше 10 сек, это не хорошо, а если более 29 сек,
    # то это превышает стандартный таймаут проверки на недогруз страницы 120 сек
    # паузу делаем в половину установленного таймаута, первую половину ждем перед поиском ответа на вопрос, вторую, перед нажатием кнопки отправки
    def __pause_for_answer(self) -> None:
        timeout_for_answer = self.__settings.get('timeout_for_answer',
                                                 config.MIN_TIMEOUT_FOR_ANSWER)

        if timeout_for_answer < 10:
            timeout_for_answer = config.MIN_TIMEOUT_FOR_ANSWER
        elif timeout_for_answer > config.MAX_TIMEOUT_FOR_ANSWER:
            timeout_for_answer = config.MAX_TIMEOUT_FOR_ANSWER

        timeout_for_answer = round(timeout_for_answer * 1000 / 2, 0)
        self.page.wait_for_timeout(timeout_for_answer)

    def __get_test_info(self) -> tuple[dict[str, int], str]:
        test_info = {}
        error_msg = ''
        result = (test_info, error_msg)

        try:
            self.page.locator('span.player-questions').wait_for()
            item = self.page.locator('span.player-questions').all()

            if len(item) == 0:
                # self.__reload('Не найден номер текущего вопроса!')
                error_msg = 'Не найден номер текущего вопроса!'
                result = (test_info, error_msg)
                return result
            else:
                value = item[0].text_content().replace('Вопрос', '').strip()

                if value.isdecimal():
                    test_info['item'] = int(value)

            questions_count = self.page.locator('span.test-sub-question').all()

            if len(questions_count) == 0:
                # self.__reload('Не найдено количество вопросов!')
                error_msg = 'Не найдено количество вопросов!'
                result = (test_info, error_msg)
                return result
            else:
                value = questions_count[0].text_content().replace(
                    'из', '').strip()

                if value.isdecimal():
                    test_info['questionsCount'] = int(value)

            questions_unanswered = self.page.locator('span.skipped').all()

            if len(questions_unanswered) == 0:
                # self.__reload('Не найдено число пропущенных вопросов!')
                error_msg = 'Не найдено число пропущенных вопросов!'
                result = (test_info, error_msg)
                return result
            else:
                value = questions_unanswered[0].text_content().replace(
                    'ПРОПУЩЕНО:', '').strip()

                if value.isdecimal():
                    test_info['questionsUnanswered'] = int(value)

        except Error as exp:
            error_msg = f'Непредвиденная ошибка при получении информации о вопросе! {exp}'
            result = (test_info, error_msg)
            return result

        result = (test_info, error_msg)
        return result

    def __get_question_type(self) -> tuple[str, str]:
        type_question = ''
        error_msg = ''
        result = (type_question, error_msg)
        form = self.page.locator('#player-assessments-form')

        try:
            form.wait_for()
        except TimeoutError:
            # self.__reload('Не удалось найти форму с вопросом!')
            error_msg = 'Не удалось найти форму с вопросом!'
            result = (type_question, error_msg)
            return result
        except Error:
            error_msg = 'Не удалось найти форму с вопросом!'
            result = (type_question, error_msg)
            return result

        for key, value in self.__matching_question_types.items():
            if form.get_by_text(key).count() == 1:
                type_question = value

        if type_question == 'match' and self.page.locator('#multipleMatchBottom').count() > 0:
            type_question = 'matchMultiple'

        result = (type_question, error_msg)
        return result

    # Выбирает и запускает функцию для ответа на вопрос определенного типа в зависимости от типа вопроса:
    # например выбор одного варианта или упорядочивание ответов или соответствие блоков
    def __searching_for_answer(self, variants_question: list[str], type_question: str) -> tuple[bool, bool, str]:
        need_skip = False
        need_reload = False
        error_msg = ''

        if type_question == 'textEntry':
            need_skip, need_reload, error_msg = self.__input_text_answer(
                variants_question, type_question)
        elif type_question == 'choice':
            need_skip, need_reload, error_msg = self.__choose_correct_answer(
                variants_question, type_question)
        elif type_question == 'choiceMultiple':
            need_skip, need_reload, error_msg = self.__choose_multiple_answers(
                variants_question, type_question)
        elif type_question == 'order':
            need_skip, need_reload, error_msg = self.__sorting_answers(
                variants_question, type_question)
        elif type_question == 'match':
            need_skip, need_reload, error_msg = self.__matching_answers(
                variants_question, type_question)
        elif type_question == 'matchMultiple':
            need_skip, need_reload, error_msg = self.__matching_multiple_answers(
                variants_question, type_question)
        elif type_question == '':
            # self.__logging('Тип вопроса неопределен!')
            need_reload = True
            error_msg = 'Тип вопроса неопределен!'
        else:
            need_skip = True
            error_msg = 'Неизвестный тип вопроса!'
            self.__count_unfound_answers += 1
            self.__logging(error_msg)
            self.__alert(error_msg)

        result = (need_skip, need_reload, error_msg)
        return result

    # Проверяет на орфографические ошибки текстового ответа
    def __spellchecking(self, text_answer: str) -> str:
        clear_text_answer = text_answer

        # если в БД ответ написан с ; после которой идет несвязанный набор букв, надо отсечь это
        if ';' in text_answer:
            clear_text_answer = text_answer.split(';')[0]

        # если слово дублируется, то возьмем только первый дуликат
        len_text_answer = len(text_answer)

        if not len_text_answer % 2:
            middle = int(len_text_answer / 2)
            part1 = text_answer[0:middle]
            part2 = text_answer[middle:]

            if part1 == part2:
                clear_text_answer = part1

        return clear_text_answer

    def __check_text_answer(self, answers: list) -> tuple[str, int]:
        result = ('', 0)

        if len(answers) == 1:
            answer = answers[0]
            id_answer = answer[0]
            id_question = answer[1]
            self.__question_block_id = answer[2]
            result = (id_answer, id_question)
        elif len(answers) > 1:
            answer = answers[0]
            id_answer = answer[0]
            id_question = answer[1]
            result = (id_answer, id_question)
            self.__logging(
                'Найдено более одного текстового ответа в БД. Беру первый попавшийся ответ!')

        return result

    # Ищет и вводит в поле текстовый ответ
    def __input_text_answer(self, variants_question: list[str], type_question: str) -> tuple[bool, bool, str]:
        error_msg = ''
        need_skip = False
        need_reload = False
        result = (need_skip, need_reload, error_msg)

        for variant in variants_question:
            answers = self.__find_answer_by_text(variant, type_question)
            id_answer, id_question = self.__check_text_answer(answers)

            if id_answer:
                if config.DEBUG:
                    print(f'ОТВЕТ НАШЕЛСЯ ПО ФРАЗЕ:\n{variant}')

                break

        if not id_answer:
            error_msg = 'Не найден текстовый ответ'
            need_skip = True
            need_reload = False
            self.__count_unfound_answers += 1
            result = (need_skip, need_reload, error_msg)
            return result
        
        if config.DEBUG:
            print(f'Найденный id ответа: {id_answer}\nНайденный id вопроса: {id_question}')

        # бывает, что в базе для текстового ввода есть больше одного ID, тексты в них одинаковы, потому берем первый
        if ',' in id_answer:
            id_answer = id_answer.split(',')[0]

        text_answer = model.get_text_answer(id_answer, id_question)

        if not text_answer:
            error_msg = 'Не найден текстовый ответ, хотя ID ответа было получено'
            need_skip = True
            need_reload = False
            self.__count_unfound_answers += 1
            result = (need_skip, need_reload, error_msg)
            return result

        clear_text_answer = self.__spellchecking(text_answer)
        textarea = self.page.locator('textarea[id=answers-]')

        try:
            textarea.type(text=clear_text_answer, delay=100)
        except TimeoutError:
            error_msg = 'Не найдено поле ввода!'
            need_skip = False
            need_reload = True
            result = (need_skip, need_reload, error_msg)
            return result
        except Error:
            error_msg = 'Не найдено поле ввода!'
            need_skip = False
            need_reload = True
            result = (need_skip, need_reload, error_msg)
            return result

        return result

    def __check_choose_correct_answer(self, answers: list[tuple]) -> tuple[str, int]:
        result = ('', 0)

        if len(answers) > 0:
            for answer in answers:
                id_answer = answer[0]
                id_question = answer[1]

                if self.page.locator(f'input[value="{id_answer}"]').count() > 0:
                    self.__question_block_id = answer[2]
                    result = (id_answer, id_question)
                    break

        return result

    # Заполняет правильный ответ из вариантов
    def __choose_correct_answer(self, variants_question: list[str], type_question: str) -> tuple[bool, bool, str]:
        error_msg = ''
        need_skip = False
        need_reload = False
        result = (need_skip, need_reload, error_msg)
        id_answer = 0

        for variant in variants_question:
            answers = self.__find_answer_by_text(variant, type_question)
            id_answer, id_question = self.__check_choose_correct_answer(answers)

            if id_answer:
                if config.DEBUG:
                    print(f'ОТВЕТ НАШЕЛСЯ ПО ФРАЗЕ:\n{variant}')

                break

        if not id_answer:
            error_msg = 'Не найден единственный правильный ответ!'
            need_skip = True
            need_reload = False
            self.__count_unfound_answers += 1
            result = (need_skip, need_reload, error_msg)
            return result

        if config.DEBUG:
            print(f'Найденный id ответа: {id_answer}\nНайденный id вопроса: {id_question}')

        radio_button = self.page.locator(f'input[value="{id_answer}"]')

        try:
            # radio_button.click(delay=200)
            radio_button.focus()
            radio_button.dispatch_event('click')
        except TimeoutError:
            # self.__reload('Не найдена галочка в ответе')
            error_msg = 'Не найдена галочка в ответе'
            need_skip = False
            need_reload = True
            result = (need_skip, need_reload, error_msg)

        return result

    # Проверяет правильность ответов и выбирает подходящий, когда их несколько в БД на один текст вопроса
    def __check_multiple_answers(self, answers: list) -> tuple[str, int]:
        result = ('', 0)

        if len(answers) > 0:
            for answer in answers:
                id_answers = answer[0]
                id_question = answer[1]
                found = True if id_answers else False

                for id_answer in id_answers.split(','):
                    if self.page.locator(f'input[value="{id_answer}"]').count() == 0:
                        found = False
                        break

                if found:
                    self.__question_block_id = answer[2]
                    result = (id_answers, id_question)
                    break

        return result

    # Заполняет несколько правильных ответов на странице
    def __choose_multiple_answers(self, variants_question: list[str], type_question: str) -> tuple[bool, bool, str]:
        error_msg = ''
        need_skip = False
        need_reload = False
        result = (need_skip, need_reload, error_msg)

        for variant in variants_question:
            answers = self.__find_answer_by_text(variant, type_question)
            id_answers, id_question = self.__check_multiple_answers(answers)

            if id_answers:
                if config.DEBUG:
                    print(f'ОТВЕТ НАШЕЛСЯ ПО ФРАЗЕ:\n{variant}')

                break

        if not id_answers:
            error_msg = 'Не найден набор правильных ответов!'
            need_skip = True
            need_reload = False
            self.__count_unfound_answers += 1
            result = (need_skip, need_reload, error_msg)
            return result
        
        if config.DEBUG:
            print(f'Найденный id ответа: {id_answers}\nНайденный id вопроса: {id_question}')

        for id_answer in id_answers.split(','):
            radio_button = self.page.locator(f'input[value="{id_answer}"]')

            try:
                radio_button.focus()
                radio_button.dispatch_event('click')
            except TimeoutError:
                error_msg = 'Не найдена галочка в ответе'
                need_skip = False
                need_reload = False
                result = (need_skip, need_reload, error_msg)

        return result

    # Проверяет соответствие ответов из БД текущим ответам на странице и возвращает ответы в правильном порядке из БД
    # current_id_answers - текущий порядок ответов на странице
    def __check_sorting_answers(self, answers: list, current_id_answers: list) -> tuple[str, int]:
        result = ('', '')

        if len(answers) > 0:
            for answer in answers:
                id_answers = answer[0]
                id_question = answer[1]
                found = True if id_answers else False

                for id_answer in id_answers.split(','):
                    if id_answer not in current_id_answers:
                        found = False
                        break

                if found:
                    self.__question_block_id = answer[2]
                    result = (id_answers, id_question)
                    break

        return result

    # Сначала проверяет корректность текущего порядка ответов и если надо перетаскивает их
    def __sorting_answers(self, variants_question: list[str], type_question: str) -> tuple[bool, bool, str]:
        error_msg = ''
        need_skip = False
        need_reload = False
        result = (need_skip, need_reload, error_msg)

        # получим все блоки ответов на странице в их текущем порядке
        current_id_answers = []
        test_answers = self.page.locator('div.test-answers').all()

        for test_answer in test_answers:
            current_id_answers.append(test_answer.locator(
                'input').get_attribute('value'))

        for variant in variants_question:
            answers = self.__find_answer_by_text(variant, type_question)
            correct_response, id_question = self.__check_sorting_answers(answers,
                                                                        current_id_answers)
            correct_id_answers = correct_response.split(',')

            if correct_id_answers:
                if config.DEBUG:
                    print(f'ОТВЕТ НАШЕЛСЯ ПО ФРАЗЕ:\n{variant}')

                break

        if current_id_answers != correct_id_answers:
            error_msg = 'Обнаружен неверный порядок ответов!'
            need_skip = True
            need_reload = False
            self.__count_unfound_answers += 1
            result = (need_skip, need_reload, error_msg)
            return result

        if config.DEBUG:
            print(f'Найденный id ответа: {correct_response}\nНайденный id вопроса: {id_question}')

        # Перетаскивание пока не реализовано в виду ненужности

        return result

    # Находит правильный набор ответов, если их несколько
    def __check_matching_answers(self, answers: list) -> tuple[str, int]:
        result = ('', 0)

        if len(answers) > 0:
            for answer in answers:
                pair_id_answers = answer[0]
                id_question = answer[1]
                found = True if pair_id_answers else False

                # разбирает ответ вида: L4vT|8Z6X,xnGo|voCq,Lsri|JtPR
                id_answers = service.RE_MATCHING.split(pair_id_answers)

                for id_answer in id_answers:
                    if self.page.locator(f'div[id="{id_answer}"]').count() == 0:
                        found = False
                        break

                if found:
                    self.__question_block_id = answer[2]
                    result = (pair_id_answers, id_question)
                    break

        return result

    # перетаскивает блоки для соответствия
    def __matching_answers(self, variants_question: list[str], type_question: str) -> tuple[bool, bool, str]:
        error_msg = ''
        need_skip = False
        need_reload = False
        result = (need_skip, need_reload, error_msg)
        # получим заполненный список левой стороны ABCD
        left_side = self.page.locator('div.docLeft div.dragItem').all()
        # получим пустые клетки правой стороны
        right_side_empty = self.page.locator('div.ui-droppable').all()
        # сформируем список пар (кортежей) левой стороны и пустых клеток(локаторов) справа
        pair_left_right = [(left_side[i], right_side_empty[i])
                           for i in range(0, len(left_side))]

        for variant in variants_question:
            answers = self.__find_answer_by_text(variant, type_question)
            correct_response, id_question = self.__check_matching_answers(answers)

            if correct_response:
                if config.DEBUG:
                    print(f'ОТВЕТ НАШЕЛСЯ ПО ФРАЗЕ:\n{variant}')

                break

        if not correct_response:
            error_msg = 'Не найден ответ для сопоставления'
            need_skip = True
            need_reload = False
            self.__count_unfound_answers += 1
            result = (need_skip, need_reload, error_msg)
            return result
        
        if config.DEBUG:
            print(f'Найденный id ответа: {correct_response}\nНайденный id вопроса: {id_question}')

        pair_id_answers = correct_response.split(',')

        for pair_id_answer in pair_id_answers:
            id_answers = pair_id_answer.split('|')
            left_id = id_answers[0]
            right_id = id_answers[1]

            # перебираем пары локаторов и если нашли совпадение id с левой стороны, то тащим правый локатор на пустой локатор который в паре с левым
            for pair in pair_left_right:
                if pair[0].get_attribute('id') == left_id:
                    block = self.page.locator(f'div[id="{right_id}"]')

                    try:
                        block.drag_to(pair[1])
                    except TimeoutError:
                        error_msg = 'Ошибка при перетаскивании блока'
                        need_skip = True
                        need_reload = False
                        self.__count_unfound_answers += 1
                        result = (need_skip, need_reload, error_msg)
                        return result
                    except Error:
                        error_msg = 'Ошибка при перетаскивании блока'
                        need_skip = True
                        self.__count_unfound_answers += 1
                        need_reload = False
                        result = (need_skip, need_reload, error_msg)
                        return result

                    break

        return result

    def __check_matching_multiple_answers(self, answers: list) -> tuple[str, int]:
        result = ('', 0)

        if len(answers) > 0:
            for answer in answers:
                pair_id_answers = answer[0]
                id_question = answer[1]
                found = True if pair_id_answers else False
                # разбирает ответ вида: '6Oj9|8GZi;Bqng;eO5U,d1jK|2SBf;B2xf;jf6o,wx9r|ZqR2;eUy3;gmkq;iNmW'
                id_answers = service.RE_MATCHING_MULTIPLE.split(pair_id_answers)

                for id_answer in id_answers:
                    if self.page.locator(f'li[data="{id_answer}"]').count() == 0:
                        found = False
                        break

                if found:
                    self.__question_block_id = answer[2]
                    result = (pair_id_answers, id_question)
                    break

        return result

    # Перетаскивает блоки по соответствий как выше, только сложнее, одному блоку соответствует несколько других
    def __matching_multiple_answers(self, variants_question: list[str], type_question: str) -> tuple[bool, bool, str]:
        error_msg = ''
        need_skip = False
        need_reload = False
        result = (need_skip, need_reload, error_msg)
        # Обработаем вариант с множественными соответствиями
        # получим заполненный список левой стороны ABC
        left_side = self.page.locator('ul.sort li').all()
        # получим пустые клетки правой стороны
        right_side_empty = self.page.locator('ul.matchRightSort').all()
        # сформируем список пар (кортежей) левой стороны и пустых клеток справа
        pair_left_right = [(left_side[i], right_side_empty[i])
                           for i in range(0, len(left_side))]

        for variant in variants_question:
            answers = self.__find_answer_by_text(variant, type_question)
            correct_response, id_question = self.__check_matching_multiple_answers(answers)

            if correct_response:
                if config.DEBUG:
                    print(f'ОТВЕТ НАШЕЛСЯ ПО ФРАЗЕ:\n{variant}')

                break

        if not correct_response:
            error_msg = 'Не найден ответ для множественного сопоставления'
            need_skip = True
            need_reload = False
            self.__count_unfound_answers += 1
            result = (need_skip, need_reload, error_msg)
            return result

        if config.DEBUG:
            print(f'Найденный id ответа: {correct_response}\nНайденный id вопроса: {id_question}')

        correct_id_answers = correct_response.split(',')

        for pair_answers in correct_id_answers:
            ids = pair_answers.split('|')
            left_id = ids[0].strip()
            right_ids = ids[1].split(';')

            # перебираем пары блоков и если нашли совпадение id с левой стороны, то тащим все правые соответствующие локаторы на пустой локатор который в паре с левым
            for pair in pair_left_right:
                if pair[0].get_attribute('data') == left_id:
                    for right_id in right_ids:

                        blocks = self.page.locator(
                            f'ul[id="answerChoises"] li[data="{right_id}"]').all()
                        block = blocks[0]

                        try:
                            block.drag_to(pair[1])
                        except TimeoutError:
                            error_msg = 'Ошибка при перетаскивании блоков!'
                            need_skip = True
                            need_reload = False
                            self.__count_unfound_answers += 1
                            result = (need_skip, need_reload, error_msg)
                            return result
                        except Error:
                            error_msg = 'Ошибка при перетаскивании блоков!'
                            need_skip = True
                            need_reload = False
                            self.__count_unfound_answers += 1
                            result = (need_skip, need_reload, error_msg)
                            return result

                    break

        return result
    
    def __find_answer_by_text(self, text_variant: str, type_question: str) -> list[tuple]:
        answers = []

        if not text_variant:
            return answers

        answers = model.get_correct_answer_info(text_variant,
                                                type_question,
                                                self.__question_block_id)

        return answers

    # проверяет, нужно ли пропустить тест если требуется сделать фиксированное число ошибок под конец теста или страница зациклена в перезагрузке
    def __need_skip_question(self) -> bool:
        result = False
        questions_count = self.__test_info.get('questionsCount', 0)
        current_question = self.__test_info.get('item', 0)
        questions_unanswered = self.__test_info.get('questionsUnanswered', 0)
        fake_errors = self.__settings.get('fake_errors', 0)
        fake_errors_count = 0

        if fake_errors:
            fake_errors_count = int(questions_count / 10)

        # сравним количество оставшихся вопросов с количеством искусственных ошибок
        if questions_count - current_question > fake_errors_count:
            return result

        # определим сколько осталось сделать ошибок
        need_errors = fake_errors_count - \
            self.__count_unfound_answers - questions_unanswered

        result = True if need_errors > 0 else False

        if config.DEBUG:
            print(f'Инфа о вопросе:\n{self.__test_info}')

        return result

    # Возвращает кортеж со списоком, где первый элемент текст вопроса без переносов строк либо путь к картинке либо иностранный текст,
    # далее идет разбивка вопроса на фразы, если это не картинка сначала по чистому тексту потом по сырому с тегами
    # а далее на отдельные слова не короче 5 символов по иностранному тексту или по тексту без тегов
    # Второй элемент это сырой вопрос с тегами
    # Третий элемент кортежа сообщение об ошибке
    def __get_question(self) -> tuple[list[str], str, str]:
        error_msg = ''
        variants_question = []
        question = self.page.locator('span.test-question-text-2')
        raw_text_question = ''

        try:
            raw_text_question = question.inner_html()
        except TimeoutError:
            error_msg = 'Ошибка при поиске вопроса!'
            result = (variants_question, raw_text_question, error_msg)
            return result
        except Error:
            error_msg = 'Ошибка при поиске вопроса!'
            result = (variants_question, raw_text_question, error_msg)
            return result

        if not raw_text_question:
            error_msg = 'Отсутствует текст или картинка вопроса!'
            result = (variants_question, raw_text_question, error_msg)
            return result

        question_images = question.locator('p img').all()

        if question_images:
            for question_img in question_images:
                img_path = question_img.get_attribute(name='src', timeout=3000)
                variants_question.append(img_path)
        else:
            only_text = question.text_content()

            # Первым в списке пусть будет сырой иностранный текст если он есть конечно
            if service.find_latinian_symbols(only_text):
                foreign_text = service.get_only_foreign_text(only_text)
                variants_question.append(foreign_text)

            # Вторым в списке вопросов пусть будет чистый текст вопроса без тегов разделенный на фразы
            # теперь заменю мнемоники HTML на их коды
            clear_only_text = service.replace_mnemonics_html(only_text)
            # clear_only_text = clear_only_text.replace('\n', '').replace('&gt;', '>').replace('&lt;', '<')
            clear_only_text = clear_only_text.replace('\n', '')

            # тут я разобью чистый текст на фразы по запятым и неразрывному пробелу
            phrases = service.get_phrsases_for_only_text(clear_only_text)
            variants_question.extend(phrases)

            # теперь тоже самое сделаю для сырого текста вопроса с тегами
            clear_raw_text_question = service.replace_mnemonics_html(raw_text_question)
            clear_raw_text_question = clear_raw_text_question.replace('\n', '')
            phrases = service.get_phrsases_for_raw_question(clear_raw_text_question)
            variants_question.extend(phrases)

            # и совсем уже отчаянный шаг, поиск по словам входящим в чистый текст, не короче 5 букв
            # эти слова добавлю в конец списка, они будут проверяться в последнюю очередь
            words = [word for word in clear_only_text.split(' ') if len(word) > 4]

            if words:
                variants_question.extend(words)

            # # если в строке есть неразрывный пробел, то обрежу строку до него или до 15 символа
            # index_end_nbsp = raw_text_question.find('&nbsp;')
            # index_end = 15 if index_end_nbsp == -1 or index_end_nbsp > 15 else index_end_nbsp

            # text_question = raw_text_question.replace('\n', '').replace('&gt;', '>').replace('&lt;', '<')
            # variants_question.append(text_question)

            # if len(raw_text_question) > index_end:
            #     first_part_question = raw_text_question[0:index_end]
            #     variants_question.append(first_part_question)

        result = (variants_question, raw_text_question, error_msg)

        return result

    # взводит флаг окончания теста, как только доходит до последнего вопроса, так как если есть неотвеченны вопросы,
    # после последнего перекидывает на неотвеченный и тест зацикливается
    def __is_last_question(self) -> str:
        error_msg = ''
        current_question = self.__test_info.get('item', -1)
        total_questions = self.__test_info.get('questionsCount', -1)

        if current_question == -1 or total_questions == -1:
            # self.__reload('Не удалось определить номера вопросов!')
            error_msg = 'Не удалось определить номера вопросов!'
            return error_msg

        self.__complete_test = (current_question == total_questions)

        if config.DEBUG:
            print(
                f'Текущий № вопроса: {current_question} всего вопросов: {total_questions} тест завершен: {self.__complete_test}')

        return error_msg

    def __skip_question(self, reason_skip: str = '') -> str:
        error_msg = ''

        if self.__manual_presskey:
            return error_msg

        button_next = self.page.locator('input.btNext')

        try:
            # button_next.click(delay=200)
            button_next.focus()
            button_next.dispatch_event('click')
        except TimeoutError:
            error_msg = 'Не удалось найти кнопку Пропустить вопрос'
            return error_msg
        except Error:
            error_msg = 'Не удалось найти кнопку Пропустить вопрос'
            return error_msg

        self.__logging(f'Вопрос пропущен: {reason_skip}')

        return error_msg

    # жмем кнопку ответить и проверяем последний ли это вопрос, если тест уже завершен, то переходим к завершению работы
    def __send_answer(self) -> str:
        error_msg = ''

        if self.__manual_presskey:
            return error_msg

        submit_button = self.page.locator('input[name=submit_send]')

        try:
            # submit_button.click(delay=200)
            submit_button.focus()
            submit_button.dispatch_event('click')
        except TimeoutError:
            error_msg = 'Не удалось найти кнопку отправки ответа.'
            return error_msg
        except Error:
            error_msg = 'Не удалось найти кнопку отправки ответа.'
            return error_msg

        self.__logging('Ответ отправлен')
        return error_msg

    # делает искусственную паузу для ручного поиска теста путем поиска несуществующего селектора
    def __pause(self, timeout: float = config.TIMEOUT_GLOBAL_PAUSE) -> None:
        try:
            self.page.locator('#selectorHasan').wait_for(
                timeout=timeout, state='attached')
        except TimeoutError:
            return
        except Error:
            return

    def __reload(self, message: str = '') -> None:
        self.page.reload()
        self.__logging(f'{message}; Обновляем страницу')

    def __finish_test(self) -> tuple[bool, str]:
        finish = False
        error_msg = ''
        result = (finish, error_msg)

        if self.__manual_presskey:
            return result

        questions_count = self.__test_info.get('questionsCount', 0)
        questions_unanswered = self.__test_info.get('questionsUnanswered', 0)

        if questions_unanswered > int(questions_count / 2):
            error_msg = 'Много неотвеченных вопросов, тест не был сдан!'
            self.__logging(error_msg)
            self.__question_block_id = 0
            self.__complete_test = False
            self.__path_log_file = ''
            self.__test_info = {}
            finish = False
            self.__alert(error_msg)
            result = (finish, error_msg)
            return result

        button_finish = self.page.locator('input.doFinishBtn')

        try:
            button_finish.focus()
            button_finish.dispatch_event('click')
        except TimeoutError:
            error_msg = 'Не удалось найти кнопку завершения теста за таймаут'
            self.__logging(error_msg)
            self.__path_log_file = ''
            finish = True
            result = (finish, error_msg)
            return result
        except Error:
            error_msg = 'Не удалось найти кнопку завершения теста'
            self.__logging(error_msg)
            self.__path_log_file = ''
            finish = True
            result = (finish, error_msg)
            return result

        self.__question_block_id = 0
        self.__complete_test = False
        self.__test_info = {}
        self.__logging('<<<<< Тест успешно завершен! >>>>>')
        self.__path_log_file = ''
        finish = True
        result = (finish, error_msg)
        return result

    def __logging(self, line: str) -> None:
        if config.DEBUG:
            print(line)

        if not self.__path_log_file:
            return

        dt = datetime.now()
        time_log = dt.strftime('%d-%m-%Y|%H:%M:%S')

        try:
            with open(self.__path_log_file, 'a', encoding='utf-8') as f:
                f.write(f'{time_log} {line}\n')
        except FileNotFoundError:
            pass

    def __create_log_file(self) -> str:
        error_msg = ''
        log_dir = 'errors'
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        try:
            student = self.page.locator('#user-profile').get_attribute('title')
        except TimeoutError:
            error_msg = 'Не удалось определить имя студента!'
            return error_msg
        except Error:
            error_msg = 'Не удалось определить имя студента!'
            return error_msg

        try:
            discipline = self.page.locator(
                'h1.player-discipline').text_content()
        except TimeoutError:
            # error_msg = 'Не удалось определить название предмета!'
            # return error_msg
            discipline = 'Нет названия предмета'
        except Error:
            # error_msg = 'Не удалось определить имя предмета!'
            # return error_msg
            discipline = 'Нет имени предмета'

        student = student.strip()
        discipline = discipline.strip()
        found_files = sorted(Path(log_dir).glob(
            f'{student}-{discipline}*.log'))
        name_log_file = ''

        if found_files:
            number_file = found_files[-1].name.split('-')[2].split('.')[0]

            if number_file.isdecimal():
                name_log_file = f'{student}-{discipline}-{int(number_file) + 1}.log'
            elif config.DEBUG:
                print(
                    f'Имя лог файла: {found_files[-1].name} оканчивается не на цифры!')
        else:
            name_log_file = f'{student}-{discipline}-1.log'

        if name_log_file:
            name_log_file = self.__delete_wrong_symbols(name_log_file)
            self.__path_log_file = f'{log_dir}/{name_log_file}'

            f = open(self.__path_log_file, 'w+', encoding='utf-8')
            f.close()

        return error_msg
     
    def __delete_wrong_symbols(self, file_name: str) -> str:
        if file_name[-1] == '.' or file_name[-1] == ' ':
            file_name[-1] = ''

        table = str.maketrans('', '', '\/:*?"<>|')
        return file_name.translate(table)

    def __alert(self, message: str) -> None:
        self.page.evaluate(f'() => alert("{message}");')

    def stop(self) -> None:
        # self.page.remove_listener('load', self.__check_begin_test)
        # self.page.remove_listener('dialog')
        self.__free_used_proxy()
        self.__context.close()
        self.__browser.close()
        self.__playwright.stop()
