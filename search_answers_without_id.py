from playwright.sync_api import Page, sync_playwright, TimeoutError, Error, expect
import sawi_model
import service
import config


def input_text_answer(page: Page, raw_text_question: str, type_question: str, path_log_file: str) -> tuple[bool, bool, str, str]:
    error_msg = ''
    need_skip = False
    need_reload = False

    answer, _ = sawi_model.find_answer(raw_text_question, type_question)

    if not answer:
        return need_skip, need_reload, error_msg, answer

    service.logging(f'Найден ответ в базе без ID: {answer}', path_log_file)
    textarea = page.locator('textarea[id=answers-]')

    try:
        textarea.type(text=answer, delay=100)
    except TimeoutError:
        error_msg = 'Не найдено поле ввода!'
        need_skip = False
        need_reload = True
    except Error:
        error_msg = 'Не найдено поле ввода!'
        need_skip = False
        need_reload = True

    return need_skip, need_reload, error_msg, answer


def choose_correct_answer(page: Page, raw_text_question: str, type_question: str, path_log_file: str) -> tuple[bool, bool, str, str]:
    error_msg = ''
    need_skip = False
    need_reload = False

    text_answer, id_answer = sawi_model.find_answer(raw_text_question,
                                                    type_question)

    # получим все варианты ответов на странице
    answers_on_page = page.locator('div.test-answers').all()

    for answer_on_page in answers_on_page:
        variant_answer = answer_on_page.text_content()

        if variant_answer is None:
            continue

        if text_answer == variant_answer.strip():
            radio_button = answer_on_page.locator('input')
            new_id_answer = radio_button.get_attribute('value')

            if new_id_answer is None:
                new_id_answer = ''

            if not id_answer:
                sawi_model.add_id_answer(raw_text_question,
                                         type_question,
                                         text_answer,
                                         new_id_answer)

            service.logging(
                f'Найден ответ в базе ответов без ID: {text_answer} - {new_id_answer}', path_log_file)

            try:
                # radio_button.click(delay=200)
                radio_button.focus()
                radio_button.dispatch_event('click')
            except TimeoutError:
                # self.__reload('Не найдена галочка в ответе')
                error_msg = 'Не найдена галочка в ответе'
                need_skip = False
                need_reload = True

            break

    return need_skip, need_reload, error_msg, id_answer


def choose_multiple_answers(page: Page, raw_text_question: str, type_question: str, path_log_file: str) -> tuple[bool, bool, str, str]:
    error_msg = ''
    need_skip = False
    need_reload = False
    new_id_answers = []  # список найденных ID ответов

    text_answers, id_answer = sawi_model.find_answer(raw_text_question,
                                                     type_question)

    # получим все варианты ответов на странице
    answers_on_page = page.locator('div.test-answers').all()

    for answer_on_page in answers_on_page:
        variant_answer = answer_on_page.text_content()

        if variant_answer is None:
            continue

        for answer in text_answers.split('&&'):
            if answer == variant_answer.strip():
                radio_button = answer_on_page.locator('input')
                new_id_answer = radio_button.get_attribute('value')

                if new_id_answer is None:
                    continue

                new_id_answers.append(new_id_answer)

                try:
                    radio_button.focus()
                    radio_button.dispatch_event('click')
                except TimeoutError:
                    error_msg = 'Не найдена галочка в ответе'
                    need_skip = False
                    need_reload = True

    if new_id_answers:
        correct_response = ','.join(new_id_answers)
        service.logging(
            f'Найден ответ в базе ответов без ID: {answer} - {correct_response}', path_log_file)

        if not id_answer:
            sawi_model.add_id_answer(raw_text_question,
                                     type_question,
                                     text_answers,
                                     correct_response)

        id_answer = correct_response

    return need_skip, need_reload, error_msg, id_answer


def check_matching_answers(page: Page, raw_text_question: str, type_question: str, path_log_file: str) -> tuple[bool, bool, str, str]:
    error_msg = ''
    need_skip = False
    need_reload = False

    text_answers, id_answer = sawi_model.find_answer(raw_text_question,
                                                     type_question)
    
    # получим все варианты ответов на странице
    # answers_on_page = page.locator('div.test-answers').all()

    left_side = page.locator('form[id="player-assessments-form"]>div>ul>div[style="float: left; width: 45%"]>li').all()
    right_side = page.locator('form[id="player-assessments-form"]>div>ul>div[style="float: right; width: 45%"]>li').all()
    
    for left_item in left_side:
        left_litera = left_item.locator('div>p').text_content()
        left_text = left_item.locator('div>div').text_content()
        
        if left_litera is not None:
            left_litera = left_litera.strip()   
        
        if left_text is not None:
            left_text = left_text.strip()
            
        # print(left_litera, left_text)
        
    for right_item in right_side:
        right_litera = right_item.locator('div>p').text_content()
        right_text = right_item.locator('div>div').text_content()
        
        if right_litera is not None:
            right_litera = right_litera.strip()   
        
        if right_text is not None:
            right_text = right_text.strip()
            
        # print(right_litera, right_text)
        
    # print(raw_text_question)
    # print(text_answers)

    return need_skip, need_reload, error_msg, id_answer
