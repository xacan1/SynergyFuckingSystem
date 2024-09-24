from synergy_parser import SynergyParser, config, Error
import model

# $env:PLAYWRIGHT_BROWSERS_PATH="0"

def main() -> None:
    model.create_proxies_db()
    sp = SynergyParser(config.START_URL)

    if not sp.get_access():
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
