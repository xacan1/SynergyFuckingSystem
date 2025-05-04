from playwright.sync_api import Page, TimeoutError, Error
import ai_model


MODEL_AI = ai_model.get_ai_model_openai()


def ai_search(question: str, name_ai: str) -> str:
    ai_answer = ''
    response = MODEL_AI.chat.completions.create(
        model=name_ai,
        messages=[
            {"role": "user", "content": question},
        ],
        temperature=.8,
        stream=False
    )
    ai_answer = response.choices[0].message.content

    if ai_answer is None:
        ai_answer = ''
    else:
        ai_answer = ai_answer.strip().replace('`', '').replace('json', '')

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
