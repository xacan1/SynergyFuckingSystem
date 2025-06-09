import model


# ********************* Работа с прокси ******************************************************************************
# Пример результата: proxy={"server": "http://83.167.122.108:1405", "username": "em7YT4", "password": "AzRAB9uc2ukp"})
def get_proxy_settings(proxy_info: dict) -> dict | None:
    proxy = {}

    if not proxy_info:
        return None

    proxy['server'] = f'http://{proxy_info["ip"]}:{proxy_info["port"]}'
    proxy['username'] = proxy_info['user']
    proxy['password'] = proxy_info['password']

    return proxy


def get_unused_proxy(use_proxy: int) -> dict:
    proxy_info = {}

    if not use_proxy:
        return proxy_info

    proxy_info = model.get_unused_proxy()
    return proxy_info


# если используем прокси, то в БД укажем что используем его
def set_used_proxy(use_proxy: int, proxy_info: dict) -> None:
    if use_proxy:
        model.set_proxy_used(proxy_info.get('ip', ''))


def free_used_proxy(use_proxy: int, proxy_info: dict) -> None:
    if use_proxy:
        model.free_proxy_used(proxy_info.get('ip', ''))
