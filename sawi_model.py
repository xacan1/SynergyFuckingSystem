import sqlite3 as sq
import config


# данный модуль содержит упрощенный поиск по базе без ID


# общая функция поиска ответа, так как все ответы текстовые в этой БД DB_ANSWERS_WITHOUT_ID отличается лишь тип и дальнейшая обработка полученного ответа
def find_answer(question: str, type_question: str) -> tuple[str, str]:
    text_answer = ''
    id_answer = ''

    with sq.connect(config.DB_ANSWERS_WITHOUT_ID) as con:
        parameters = (question, type_question,)
        cur = con.cursor()
        cur.execute("""
        SELECT correctTextAnswer, correctResponse FROM question_answers 
        WHERE question=? AND questionType=?
        """, parameters)

        row = cur.fetchone()

        if row:
            text_answer = row[0]
            id_answer = row[1]

    return text_answer, id_answer


# Сохраняет id_answer в БД для ответа если correctResponse пустое
def add_id_answer(question: str, type_question: str, answer: str, correct_response: str) -> None:
    with sq.connect(config.DB_ANSWERS_WITHOUT_ID) as con:
        parameters = (correct_response, question, type_question, answer, '',)
        cur = con.cursor()
        cur.execute("""
        UPDATE question_answers SET correctResponse=? 
        WHERE question=? AND questionType=? AND correctTextAnswer=? AND correctResponse=?
        """, parameters)


# Возвращает id ответа, id вопроса и id блока вопросов в списке, так как количество найденных ответов может быть больше чем 1 и надо будет решать коллизию
# Что бы коллизий не было, надо передавать id блока вопросов, так как вопросы могут дублироваться,
# но найти id блока вопросов возможно только при нахождении хотя бы одного единственного ответа
# так что первый ответ по возможности будет использован для нахождения блока вопросов, что бы в дальнейшем его передавать в функцию вместо пустой строки
def get_correct_answer_info(question: str, type_question: str, question_block_id: int = 0) -> list[tuple]:
    answer_info = []

    with sq.connect(config.DB_ANSWERS_WITHOUT_ID) as con:
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
