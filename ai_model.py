from yandex_cloud_ml_sdk import YCloudML
from openai import OpenAI
import config


def get_ai_model_yandexgpt():
    sdk = YCloudML(folder_id=config.FOLDER_ID_YANDEXGPT,
                   auth=config.API_KEY_YANDEXGPT)
    model = sdk.models.completions('yandexgpt')
    model = model.configure(temperature=0.3)

    return model


def get_ai_model_openai():
    client = OpenAI(api_key=config.API_KEY_DEEPSEEK,
                    base_url='https://api.deepseek.com')

    return client
