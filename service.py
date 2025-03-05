import re
import json
from ctypes import wintypes, windll, byref, create_unicode_buffer
import winreg
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
        with winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, 'Software\SFS') as key:
            value, type_value = winreg.QueryValueEx(key, 'SFS_key')
            result = (value == config.KEY_ACCESS_VALUE)
    except FileNotFoundError:
        if config.DEBUG:
            print('Не найден ключ защиты')

    return result


def load_json(s: str) -> tuple[dict, bool, bool, str]:
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
