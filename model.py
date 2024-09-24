import sqlite3 as sq
import config


def create_proxies_db() -> None:
    with sq.connect(config.DB_PROXIES_FILE_NAME) as con:
        cur = con.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS proxies(
        id INTEGER PRIMARY KEY,
        ip TEXT NOT NULL UNIQUE,
        port TEXT NOT NULL,
        user TEXT NOT NULL,
        password TEXT NOT NULL,
        used INTEGER DEFAULT 0)
        """)


def set_proxy_used(ip: str) -> None:
    if not ip:
        return

    with sq.connect(config.DB_PROXIES_FILE_NAME) as con:
        used = 0
        parameters = (ip,)
        cur = con.cursor()
        cur.execute("""
        SELECT used FROM proxies
        WHERE ip=?
        """, parameters)
        row = cur.fetchone()

        if row:
            used = row[0]

        used += 1
        parameters = (used, ip)
        cur.execute("""
        UPDATE proxies SET
        used=?
        WHERE ip=?
        """, parameters)


def free_proxy_used(ip: str) -> None:
    if not ip:
        return

    with sq.connect(config.DB_PROXIES_FILE_NAME) as con:
        used = 1
        parameters = (ip,)
        cur = con.cursor()
        cur.execute("""
        SELECT used FROM proxies
        WHERE ip=?
        """, parameters)
        row = cur.fetchone()

        if row:
            used = row[0]

        used -= 1
        parameters = (used, ip)
        cur = con.cursor()
        cur.execute("""
        UPDATE proxies SET
        used=?
        WHERE ip=?
        """, parameters)


# получает первый не использующийся прокси
def get_unused_proxy() -> dict:
    proxy_info = {}

    with sq.connect(config.DB_PROXIES_FILE_NAME) as con:
        cur = con.cursor()
        cur.execute("""
        SELECT ip, port, user, password FROM proxies
        WHERE used<4
        """)
        row = cur.fetchone()

        if row:
            proxy_info['ip'] = row[0]
            proxy_info['port'] = row[1]
            proxy_info['user'] = row[2]
            proxy_info['password'] = row[3]

    return proxy_info

# ******************************
# Работа с базой ответов
# ******************************


#  НЕИСПОЛЬЗУЕТСЯ находит id блока вопросов по наименованию, этот id нужен для точного нахождения вопроса
def get_question_block_id(title: str) -> int:
    question_block_id = 0

    with sq.connect(config.DB_ANSWERS_FILE_NAME) as con:
        parameters = (f'{title}*',)
        cur = con.cursor()
        cur.execute("""
        SELECT questionBlockId FROM question_blocks 
        WHERE title GLOB ?
        """, parameters)
        row = cur.fetchone()

        if row:
            question_block_id = row[0]

    return question_block_id


# НЕИСПОЛЬЗУЕТСЯ Функция для ситуации когда тип вопроса - choice - то есть нужно выбрать только один правильный ответ из списка.
# проверяет переданный id ответа в таблице вопросов, где уже указан id верного ответа и полный текст вопроса с html тегами
def check_answer(question: str, response: str) -> bool:
    result = False

    with sq.connect(config.DB_ANSWERS_FILE_NAME) as con:
        parameters = (question, f'*{response}*')
        cur = con.cursor()
        cur.execute("""
        SELECT correctResponse, questionType FROM questions 
        WHERE question=? and GLOB ? 
        """, parameters)
        row = cur.fetchone()
        result = True if row else False

    return result


# Возвращает id ответа, id вопроса и id блока вопросов в списке, так как количество найденных ответов может быть больше чем 1 и надо будет решать коллизию
# Что бы коллизий не было, надо передавать id блока вопросов, так как вопросы могут дублироваться,
# но найти id блока вопросов возможно только при нахождении хотя бы одного единственного ответа
# так что первый ответ по возможности будет использован для нахождения блока вопросов, что бы в дальнейшем его передавать в функцию вместо пустой строки
def get_correct_answer_info(question: str, type_question: str, question_block_id: int = 0) -> list[tuple]:
    answer_info = []

    with sq.connect(config.DB_ANSWERS_FILE_NAME) as con:
        if question_block_id:
            parameters = ('', f'*{question}*', type_question,
                          question_block_id)
            additional_filter = ' AND questionBlockId=?'
        else:
            parameters = ('', f'*{question}*', type_question)
            additional_filter = ''

        cur = con.cursor()
        cur.execute(f"""
        SELECT correctResponse, questionId, questionBlockId FROM questions 
        WHERE correctResponse!=? AND question GLOB ? AND questionType=?{additional_filter}
        """, parameters)
        rows = cur.fetchall()

        if rows:
            answer_info = rows

    return answer_info


# получает текст ответа по его id (нужно когда требуется напечатать ответ в поле)
def get_text_answer(identifier: str, id_question: int = 0) -> str:
    text_answer = ''

    if id_question:
        parameters = (identifier, id_question)
        additional_filter = ' AND questionId=?'
    else:
        parameters = (identifier,)
        additional_filter = ''

    with sq.connect(config.DB_ANSWERS_FILE_NAME) as con:
        cur = con.cursor()
        cur.execute(f"""
        SELECT answer FROM question_answers 
        WHERE identifier=?{additional_filter}
        """, parameters)
        row = cur.fetchone()

        if row:
            text_answer = row[0]

    return text_answer
