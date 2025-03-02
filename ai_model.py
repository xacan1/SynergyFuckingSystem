from yandex_cloud_ml_sdk import YCloudML
import config


def get_ai_model():
    sdk = YCloudML(folder_id=config.FOLDER_ID, auth=config.API_KEY)
    model = sdk.models.completions('yandexgpt')
    model = model.configure(temperature=0.3)
    return model
