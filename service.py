import re


RE_MATCHING = re.compile('[|,]')
RE_MATCHING_MULTIPLE = re.compile('[|;,]')
RE_LATINIAN = re.compile(r'[A-Za-z]')
RE_GET_LATINIAN_TEXT = re.compile(r'[^А-Яа-яЁё\s]+')
RE_PATTERN_PHRASES = re.compile(r'&hellip;|&nbsp;|\xa0|,') # тут всякий мусор по которому было бы хорошо поделить текст на фразы(троеточие, неразрывный пробел, запятая)
RE_RUSSIAN = re.compile(r'^[а-яА-ЯЁё]')


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
