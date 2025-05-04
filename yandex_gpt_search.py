from playwright.sync_api import Page, TimeoutError, Error
import ai_model


MODEL_AI = ai_model.get_ai_model_yandexgpt()


def ai_search(question: str) -> str:
    ai_answer = ''
    result = MODEL_AI.run(f'{question}')

    if result:
        ai_answer = result[0].text
        ai_answer = ai_answer.replace('`', '')

    return ai_answer.strip()


def get_text_answer(page: Page) -> str:
    raw_text_question = ''

    target_html = page.locator('form[id="player-assessments-form"]')
    question = target_html.locator('span.test-question-text-2')

    try:
        raw_text_question = question.inner_html()
    except TimeoutError:
        return raw_text_question
    except Error:
        return raw_text_question

    return raw_text_question
