from playwright.sync_api import Page, TimeoutError, Error
import json
import ai_model


MODEL_AI = ai_model.get_ai_model()


def ai_search(question: str, supplement: str = '') -> str:
    ai_answer = ''
    result = MODEL_AI.run(f'{supplement} {question}')

    if result:
        ai_answer = result[0].text
        ai_answer = ai_answer.replace('`', '')

    return ai_answer


def get_text_answer(page: Page) -> str:
    raw_text_question = ''
    target_html = page.locator('form[id="player-assessments-form"]')
    question = target_html.locator('span.test-question-text-2')
    question_images = question.locator('p img').all()

    # если в вопросе есть картинка, то это пока что не может быть обработано YandexGPT
    if question_images:
        return raw_text_question

    try:
        raw_text_question = question.inner_html()
    except TimeoutError:
        return raw_text_question
    except Error:
        return raw_text_question

    return raw_text_question


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
        variants_answers[id_answer] = text_answer.text_content()

    try:
        result = json.dumps(variants_answers, ensure_ascii=False)
    except json.JSONDecodeError as exp:
        print(exp)
        return result

    return result
