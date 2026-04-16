from yandex_ai_studio_sdk import AIStudio
from yandex_ai_studio_sdk.exceptions import AioRpcError
from openai import OpenAI
import config


def get_ai_model_yandexgpt():
    sdk = AIStudio(folder_id=config.FOLDER_ID_YANDEXGPT,
                   auth=config.API_KEY_YANDEXGPT)
    model = sdk.models.completions('yandexgpt')
    model = model.configure(temperature=0.3)

    return model


def get_ai_model_openai():
    client = OpenAI(api_key=config.API_KEY_DEEPSEEK,
                    base_url='https://api.deepseek.com')

    return client
