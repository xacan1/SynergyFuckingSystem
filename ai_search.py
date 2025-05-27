from playwright.sync_api import Page
import json
import time
import yandex_gpt_search
import deepseek_search
import model


def ai_search(question: str, name_ai: str) -> tuple[str, str]:
    ai_answer = ''
    error_msg = ''

    if name_ai == 'deepseek-chat' or name_ai == 'deepseek-reasoner':
        ai_answer = deepseek_search.ai_search(question, name_ai)
    elif name_ai == 'yandexgpt':
        ai_answer = yandex_gpt_search.ai_search(question)
    else:
        error_msg = 'Неверное имя нейросети!'

    return ai_answer, error_msg


def get_text_answer(page: Page, name_ai: str) -> str:
    raw_text_question = ''

    if name_ai == 'deepseek-chat' or name_ai == 'deepseek-reasoner':
        raw_text_question = deepseek_search.get_text_answer(page)
    elif name_ai == 'yandexgpt':
        raw_text_question = yandex_gpt_search.get_text_answer(page)

    return raw_text_question


def have_image_in_question(page: Page) -> bool:
    target_html = page.locator('form[id="player-assessments-form"]')
    question = target_html.locator('span.test-question-text-2')
    question_images = question.locator('p img').all()

    return True if question_images else False


def get_variants_answers_for_choice(page: Page, choice_multiple: bool) -> str:
    result = ''
    target_html = page.locator('form[id="player-assessments-form"]')

    if choice_multiple:
        answers = target_html.locator('input[name="answers[]"]').all()
    else:
        answers = target_html.locator('input[name="answers"]').all()

    if not answers:
        return result

    variants_answers = {}

    for answer in answers:
        id_answer = answer.get_attribute('value')
        text_answer = target_html.locator(f'label[for="answers-{id_answer}"]')
        variants_answers[id_answer] = text_answer.text_content().strip() # type: ignore

    try:
        result = json.dumps(variants_answers, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    return result


def get_variants_answers_for_sort(page: Page) -> str:
    result = ''
    target_html = page.locator('form[id="player-assessments-form"]')
    answers = target_html.locator('div.test-answers').all()

    if not answers:
        return result

    variants_answers = {}

    for answer in answers:
        input_answer = answer.locator('input[name="answers[]"]')
        id_answer = input_answer.get_attribute('value')
        text_answer = input_answer.text_content().strip().replace(' ', '') # type: ignore
        variants_answers[id_answer] = text_answer

    try:
        result = json.dumps(variants_answers, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    return result


def get_variants_answers_for_sort_sequence(page: Page) -> str:
    result = ''
    target_html = page.locator('form[id="player-assessments-form"]')
    answers_texts = target_html.locator('li.sequence_answer_variant').all()
    literas = target_html.locator('li.ui-draggable').all()

    if not answers_texts or not literas:
        return result

    variants_answers = {}

    for i in range(0, len(answers_texts)):
        id_answer = literas[i].get_attribute('data')
        text = answers_texts[i].inner_text()
        variants_answers[id_answer] = text

    try:
        result = json.dumps(variants_answers, ensure_ascii=False)
    except json.JSONDecodeError:
        pass

    return result


# формирует два JSON для левой стороны и нижних блоков для сопоставления между ними
def get_variants_answers_for_match(page: Page) -> tuple[str, str]:
    result = ('', '')
    target_html = page.locator('form[id="player-assessments-form"]')
    question_blocks = target_html.locator(
        'div[style="min-height: 60px; box-sizing: border-box;"]').all()
    left_side = target_html.locator('div.docLeft>div.dragItem').all()
    bottom_side = target_html.locator('div.docBottom>div.ui-draggable').all()

    block_left = {}
    block_bottom = {}

    for answer in left_side:
        litera_variant = answer.inner_text()
        id_answer = answer.get_attribute('id')

        for element in question_blocks:
            text_element = element.inner_text().strip().split('.')

            if len(text_element) < 2:
                continue

            if text_element and text_element[0] == litera_variant:
                block_left[id_answer] = text_element[1].strip()

    for answer in bottom_side:
        litera_variant = answer.inner_text()
        id_answer = answer.get_attribute('id')

        for element in question_blocks:
            text_element = element.inner_text().strip().split('.')

            if len(text_element) < 2:
                continue

            if text_element and text_element[0] == litera_variant:
                block_bottom[id_answer] = text_element[1].strip()

    try:
        left = json.dumps(block_left, ensure_ascii=False)
        bottom = json.dumps(block_bottom, ensure_ascii=False)
    except json.JSONDecodeError:
        return result

    result = (left, bottom)
    return result


def get_variants_answers_for_match_multiple(page: Page) -> tuple[str, str]:
    result = ('', '')
    target_html = page.locator('form[id="player-assessments-form"]')
    question_blocks = target_html.locator('div.test-answers').all()
    left_side = target_html.locator('td.matchLeft>ul.sort>li').all()
    bottom_side = target_html.locator('li.ui-draggable').all()

    block_left = {}
    block_bottom = {}

    for answer in left_side:
        litera_variant = answer.inner_text()
        id_answer = answer.get_attribute('data')

        for element in question_blocks:
            parts = element.locator('div').all()
            litera = parts[0].inner_text().replace('.', '')
            text = parts[1].inner_text()

            if litera == litera_variant:
                block_left[id_answer] = text

    for answer in bottom_side:
        litera_variant = answer.inner_text()
        id_answer = answer.get_attribute('data')

        for element in question_blocks:
            parts = element.locator('div').all()
            litera = parts[0].inner_text().replace('.', '')
            text = parts[1].inner_text()

            if litera == litera_variant:
                block_bottom[id_answer] = text

    try:
        left = json.dumps(block_left, ensure_ascii=False)
        bottom = json.dumps(block_bottom, ensure_ascii=False)
    except json.JSONDecodeError:
        return result

    result = (left, bottom)
    return result


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
            model.save_incorrect_answer(question_answer)
        else:
            model.save_correct_answer(question_answer)
