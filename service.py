from playwright.sync_api import Page, TimeoutError, Error
from pathlib import Path
from datetime import datetime
from ctypes import wintypes, windll, byref, create_unicode_buffer
import re
import json
import winreg
import time
import model
import config


RE_MATCHING = re.compile('[|,]')
RE_MATCHING_MULTIPLE = re.compile('[|;,]')
RE_LATINIAN = re.compile(r'[A-Za-z]')
# тут всякий мусор по которому было бы хорошо поделить текст на фразы(троеточие, неразрывный пробел, запятая)
RE_GET_LATINIAN_TEXT = re.compile(r'[^А-Яа-яЁё\s]+')
RE_PATTERN_PHRASES = re.compile(r'&hellip;|&nbsp;|\xa0|,')
RE_RUSSIAN = re.compile(r'^[а-яА-ЯЁё]')
RE_LATINIAN_AND_DIGITAL = re.compile(r'[^A-Za-z0-9]')


# проверим есть ли в строке хоть одна не латинская буква и не цифра
def find_not_latinian_and_digital(text: str) -> bool:
    if RE_LATINIAN_AND_DIGITAL.search(text) is None:
        return False
    else:
        return True


# проверю структуру ответа AI при втипе вопроса Match. В левой и правой части словаря допускаются только строки с латинскими буквами и цифрами
def validate_dict_answer(json_answer: dict) -> bool:
    result = True

    for key, value in json_answer.items():
        if find_not_latinian_and_digital(key) or find_not_latinian_and_digital(value):
            result = False
            break

    return result


# проверим есть ли хоть одна латинская буква
def find_latinian_symbols(text_question: str) -> bool:
    if RE_LATINIAN.search(text_question) is None:
        return False
    else:
        return True


# заменю некоторые ПЕЧАТНЫЕ мнемоники HTML на их коды, так записано в БД ответов.
def replace_mnemonics_html(text_question: str) -> str:
    mnemonics = {
        '…': '&hellip;',
        '–': '&ndash;',
        '«': '&laquo;',
        '»': '&raquo;',
    }

    for key, value in mnemonics.items():
        text_question = text_question.replace(key, value)

    return text_question


# Удаляет мусорные слова из-за которых поиск по БД становится очень долгим
def delete_spam_words(variants_question: list[str]) -> list[str]:
    spam_words = [
        'Неверно',
    ]

    for spam in spam_words:
        try:
            variants_question.remove(spam)
        except ValueError:
            continue

    return variants_question


def get_only_foreign_text(text_question: str) -> str:
    # отделю иностранный текст от русского если он есть
    foreign_words = RE_GET_LATINIAN_TEXT.findall(text_question)
    # уберем точки и запятые, то что не удалось убрать в регулярке
    foreign_words = [
        word for word in foreign_words if word != '.' and word != ',']
    # соберу из слов иностранную фразу и добавлю ее в варианты
    foreign_text = ' '.join(foreign_words)

    return foreign_text


def get_phrsases_for_only_text(text_question: str) -> list[str]:
    # разобью текст на фразы по запятым и неразрывному пробелу
    phrases = RE_PATTERN_PHRASES.split(text_question)
    # удалю все фразы короче 5 символов
    phrases = [phrase.strip() for phrase in phrases if len(phrase) > 4]
    phrases = sorted(phrases, key=len, reverse=True)

    return phrases


def get_phrsases_for_raw_question(text_question: str) -> list[str]:
    # разобью текст на фразы по запятым и неразрывному пробелу
    phrases = RE_PATTERN_PHRASES.split(text_question)
    # удалю из списка фразы без кириллицы, так как 99.9% там одни теги и стили или фраза меньше 5 символов
    phrases = [phrase for phrase in phrases if RE_RUSSIAN.search(
        phrase) is not None and len(phrase) > 4]
    phrases = sorted(phrases, key=len, reverse=True)

    return phrases


# получает PID активного окна
def get_active_window_pid() -> int:
    pid = wintypes.DWORD()
    active_hwnd = windll.user32.GetForegroundWindow()
    active_window_pid = windll.user32.GetWindowThreadProcessId(
        active_hwnd, byref(pid))
    return active_window_pid


# не используется, получает имя активного окна
def get_foreground_window_title() -> str:
    active_hwnd = windll.user32.GetForegroundWindow()
    length = windll.user32.GetWindowTextLengthW(active_hwnd)
    buf = create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(active_hwnd, buf, length + 1)
    return buf.value if buf.value else ''


def get_access() -> bool:
    result = False

    try:
        with winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, r'Software\SFS') as key:  # type: ignore
            value, type_value = winreg.QueryValueEx(key, 'SFS_key')
            result = (value == config.KEY_ACCESS_VALUE)
    except FileNotFoundError:
        if config.DEBUG:
            print('Не найден ключ защиты')

    return result


# Получает ответ от AI в виде словаря
def load_json(s: str) -> tuple[dict[str,str], bool, bool, str]:
    error_msg = ''
    need_skip = False
    need_reload = False
    json_answer = {}

    try:
        json_answer = json.loads(s)
    except json.JSONDecodeError:
        error_msg = 'Ошибка при загрузке JSON ответа AI.'
        need_skip = True
        need_reload = False
        result = (json_answer, need_skip, need_reload, error_msg)
        return result
    except TypeError:
        error_msg = 'Ошибка при загрузке JSON ответа AI.'
        need_skip = True
        need_reload = False
        result = (json_answer, need_skip, need_reload, error_msg)
        return result

    result = (json_answer, need_skip, need_reload, error_msg)
    return result


def load_settings() -> dict:
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
                value = value.strip()

            settings[parameter] = value

    return settings


def delete_wrong_symbols(file_name: str) -> str:
    if file_name[-1] == '.' or file_name[-1] == ' ':
        file_name[-1] = ''  # type: ignore

    table = str.maketrans('', '', r'\/:*?"<>|')  # type: ignore
    return file_name.translate(table)


def create_log_file(page: Page, discipline: str) -> tuple[str, str]:
    path_log_file = ''
    error_msg = ''
    log_dir = 'errors'
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    try:
        student = page.locator('#user-profile').get_attribute('title')
    except TimeoutError:
        error_msg = 'Не удалось определить имя студента!'
        return path_log_file, error_msg
    except Error:
        error_msg = 'Не удалось определить имя студента!'
        return path_log_file, error_msg

    student = student.strip()  # type: ignore
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
        name_log_file = delete_wrong_symbols(name_log_file)
        path_log_file = f'{log_dir}/{name_log_file}'

        f = open(path_log_file, 'w+', encoding='utf-8')
        f.close()

    return path_log_file, error_msg


def logging(line: str, path_log_file: str) -> None:
    if config.DEBUG:
        print(line)

    if not path_log_file:
        return

    dt = datetime.now()
    time_log = dt.strftime('%d-%m-%Y|%H:%M:%S')

    try:
        with open(path_log_file, 'a', encoding='utf-8') as f:
            f.write(f'{time_log} {line}\n')
    except FileNotFoundError:
        pass


def get_check_list_result_test(page: Page) -> dict:
    result_test = {}
    # page.locator('a[id="statistic"]').wait_for()
    result_links = page.locator('a[id="statistic"]').all()
    last_link = result_links[-1]

    try:
        last_link.focus()
        last_link.dispatch_event('click')
    except TimeoutError:
        return result_test

    time.sleep(1)
    # page.locator('table.table-corpus').wait_for()
    table_result = page.locator('table.table-corpus tbody tr').all()

    for row in table_result:
        tds = row.locator('td').all()

        if len(tds) > 3:
            result_test[tds[1].inner_html().strip()] = tds[3].inner_text()

    return result_test


# проверка ответов на форме завершения теста и запись результатов в БД
def check_and_save_result_test(page: Page, questions_answers: list[dict]):
    check_list = get_check_list_result_test(page)

    for question_answer in questions_answers:
        question = question_answer.get('question', '')

        if not question:
            continue

        result = check_list.get(question, '').lower()

        if 'не' in result:
            type_question = question_answer.get('questionType', '')
            title_discipline = question_answer.get('questionBlock', '')
            correct_response = question_answer.get('correctResponse', '')
            question_block_id = model.get_question_block_id(title_discipline)
            # вдруг данный ответ является не верным, а он записан в базе. Очистим его.
            model.clear_response_question(
                question, type_question, question_block_id, correct_response)
            model.save_incorrect_answer(question_answer)
        else:
            model.save_correct_answer(question_answer)
