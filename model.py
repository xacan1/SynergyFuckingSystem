import sqlite3 as sq
from datetime import datetime
from service import load_settings
import config


SETTINGS = load_settings()
PATH_AI_DB = SETTINGS.get('path_db', '')


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


def create_ai_answers_db() -> None:
    with sq.connect(f'{PATH_AI_DB}\{config.DB_AI_ANSWERS_FILE_NAME}') as con:  # type: ignore
        cur = con.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS question_blocks(
        questionBlockId INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_question_blocks_title ON question_blocks(title);
        CREATE TABLE IF NOT EXISTS question_answers(
        questionId INTEGER PRIMARY KEY AUTOINCREMENT,
        questionBlockId INTEGER NOT NULL,
        question TEXT NOT NULL,
        questionType TEXT NOT NULL,
        correctResponse TEXT NOT NULL,
        created TEXT NOT NULL,
        FOREIGN KEY (questionBlockId) REFERENCES question_blocks(questionBlockId));
        CREATE INDEX IF NOT EXISTS idx_question_answers_questionBlockId ON question_answers(questionBlockId);
        CREATE INDEX IF NOT EXISTS idx_question_answers_question ON question_answers(question);
        CREATE INDEX IF NOT EXISTS idx_question_answers_questionType ON question_answers(questionType);
        CREATE TABLE IF NOT EXISTS incorrect_responses(
        responseId INTEGER PRIMARY KEY AUTOINCREMENT,
        questionId INTEGER NOT NULL,
        incorrectResponse TEXT NOT NULL,
        FOREIGN KEY (questionId) REFERENCES question_answers(responseId));
        CREATE INDEX IF NOT EXISTS idx_incorrect_responses_questionId ON incorrect_responses(questionId)
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


# ********************************************************************
# Работа с базой AI которая постепенно формируется
# ********************************************************************


# Записывает новый блок вопросов в базу AI
def save_new_question_block(con: sq.Connection, title_discipline: str) -> int:
    parameters = (title_discipline,)
    cur = con.cursor()
    cur.execute('INSERT INTO question_blocks (title) VALUES (?)',
                parameters)
    con.commit()
    question_block_id = get_question_block_id(title_discipline)

    return question_block_id


# Записывает новый вопрос в базу AI
def save_new_question(con: sq.Connection, question: str, question_type: str, question_block_id: int, correct_response: str) -> int:
    cur = con.cursor()
    parameters = (question, question_type,
                  correct_response, question_block_id, datetime.now().date(),)
    cur.execute("""
    INSERT INTO question_answers (question, questionType, correctResponse, questionBlockId, created)
    VALUES (?,?,?,?,?)
    """, parameters)
    con.commit()
    question_id = get_question_id(question,
                                  question_type,
                                  question_block_id)

    return question_id


# возвращает список найденных корректных ответов (возможны колизии) из базы AI
def get_correct_answer_info_from_ai_answers(question: str, type_question: str, discipline: str) -> list[tuple[str, int, int]]:
    answer_info = []
    # question_block_id = get_question_block_id(discipline)

    # if not question_block_id:
    #     return answer_info

    with sq.connect(f'{PATH_AI_DB}\{config.DB_AI_ANSWERS_FILE_NAME}') as con:  # type: ignore
        parameters = ('', question, type_question)
        cur = con.cursor()
        cur.execute("""
        SELECT correctResponse, questionId, questionBlockId FROM question_answers 
        WHERE correctResponse!=? AND question=? AND questionType=?
        """, parameters)
        rows = cur.fetchall()

        if rows:
            answer_info = rows

    return answer_info


# ищем блок вопросов по названию дисциплины
def get_question_block_id(title_discipline: str) -> int:
    question_block_id = 0

    with sq.connect(f'{PATH_AI_DB}\{config.DB_AI_ANSWERS_FILE_NAME}') as con:  # type: ignore
        parameters = (title_discipline,)
        cur = con.cursor()
        cur.execute("""
        SELECT questionBlockId FROM question_blocks 
        WHERE title=?
        """, parameters)
        row = cur.fetchone()

        if row:
            question_block_id = row[0]
        else:
            question_block_id = save_new_question_block(con, title_discipline)

    return question_block_id


def get_question_id(question: str, question_type: str, question_block_id: int, correct_response: str = '') -> int:
    question_id = 0

    with sq.connect(f'{PATH_AI_DB}\{config.DB_AI_ANSWERS_FILE_NAME}') as con:  # type: ignore
        cur = con.cursor()
        parameters = (question, question_type, question_block_id,)
        cur.execute("""
        SELECT questionId FROM question_answers 
        WHERE question=? and questionType=? and questionBlockId=?
        """, parameters)
        row = cur.fetchone()

        if row:
            question_id = row[0]
        else:
            question_id = save_new_question(con,
                                            question,
                                            question_type,
                                            question_block_id,
                                            correct_response)

    return question_id


# Запись верного ответа от AI в специальную базу ответов
def save_correct_answer(question_answer: dict) -> None:
    title_discipline = question_answer.get('questionBlock')
    question_block_id = get_question_block_id(
        title_discipline)  # type: ignore

    with sq.connect(f'{PATH_AI_DB}\{config.DB_AI_ANSWERS_FILE_NAME}') as con:  # type: ignore
        question = question_answer.get('question')
        question_type = question_answer.get('questionType')
        correct_response = question_answer.get('correctResponse')
        save_new_question(con,
                          question,  # type: ignore
                          question_type,  # type: ignore
                          question_block_id,
                          correct_response)  # type: ignore


def get_incorrect_response_id(incorrect_response: str, question_id: int) -> int:
    incorrect_response_id = 0

    with sq.connect(f'{PATH_AI_DB}\{config.DB_AI_ANSWERS_FILE_NAME}') as con:  # type: ignore
        cur = con.cursor()
        parameters = (question_id, incorrect_response,)
        cur.execute("""
        SELECT responseId FROM incorrect_responses 
        WHERE questionId=? and incorrectResponse=?
        """, parameters)
        row = cur.fetchone()

        if row:
            incorrect_response_id = row[0]

    return incorrect_response_id


# Запись неверного ответа от AI в специальную таблицу ответов
def save_incorrect_answer(question_answer: dict) -> None:
    if question_answer.get('questionType') == 'textEntry':
        return

    with sq.connect(f'{PATH_AI_DB}\{config.DB_AI_ANSWERS_FILE_NAME}') as con:  # type: ignore
        title_discipline = question_answer.get('questionBlock')
        question_block_id = get_question_block_id(
            title_discipline)  # type: ignore
        cur = con.cursor()

        question = question_answer.get('question')
        question_type = question_answer.get('questionType')
        question_id = get_question_id(question,  # type: ignore
                                      question_type,  # type: ignore
                                      question_block_id)

        incorrect_response = question_answer.get('correctResponse')
        incorrect_response_id = get_incorrect_response_id(incorrect_response,  # type: ignore
                                                          question_id)

        if not incorrect_response_id:
            parameters = (incorrect_response, question_id,)
            cur.execute("""
            INSERT INTO incorrect_responses (incorrectResponse, questionId)
            VALUES (?,?)
            """, parameters)
            con.commit()
