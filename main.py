from synergy_parser import SynergyParser, config, Error
from service import get_access
import model

# pyinstaller -F -w --collect-datas=fake_useragent --icon=AvaHack.ico main.py
# $env:PLAYWRIGHT_BROWSERS_PATH="0"
# kalachevg@icloud.com
# Kalachevmark3005.
# https://lms.synergy.ru/edudoc/close/29608623/0/2662863
# https://lms.synergy.ru/edudoc/attempt/29608623/2/2662863


def main() -> None:
    model.create_proxies_db()
    model.create_ai_answers_db()
    sp = SynergyParser(config.START_URL)

    if not get_access():
        return

    try:
        sp.start_manually()
    except Error as exp:
        if config.DEBUG:
            print(f'Общая ошибка: {exp}')
    finally:
        model.free_proxy_used(sp.proxy_info.get('ip', ''))


if __name__ == '__main__':
    main()
