import logging
import os
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler
import sys

import requests
from dotenv import load_dotenv
from telebot import TeleBot


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

TOKEN_NAMES = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


MISSING_TOKENS_MESSAGE = 'Отсутствуют обязательные переменные окружения: {}'
BOT_SENT_MESSAGE_TEMPLATE = 'Бот отправил сообщение: {}'
SEND_MESSAGE_ERROR_TEMPLATE = 'Сбой при отправке сообщения: {}'
REQUEST_ERROR_MESSAGE = 'Сбой в работе программы: {}'
API_STATUS_CODE_ERROR = (
    'Код ответа API: {}. Запрос: {}, заголовки: {}, параметры: {}'
)
API_RESPONSE_ERROR = 'API вернуло ошибку: {} - {}'
RESPONSE_NOT_DICT_MESSAGE = 'Ответ API не является словарем: {}'
RESPONSE_MISSING_KEYS_MESSAGE = 'Отсутствуют ожидаемые ключи в ответе API: {}'
RESPONSE_HOMEWORKS_NOT_LIST_MESSAGE = (
    'Некорректный формат данных домашних работ '
    '(ожидается список, получено {})'
)
MISSING_HOMEWORK_NAME_MESSAGE = (
    "Отсутствует ключ 'homework_name' в информации о домашней работе."
)
MISSING_HOMEWORK_STATUS_MESSAGE = (
    "Отсутствует ключ 'status' в информации о домашней работе."
)
UNEXPECTED_HOMEWORK_STATUS_MESSAGE = 'Неожиданный статус работы: {}'
NO_NEW_UPDATES_MESSAGE = 'Нет новых обновлений'
NETWORK_ERROR_MESSAGE = 'Сетевая ошибка'
STATUS_CHANGED_MESSAGE = 'Изменился статус проверки работы "{}". {}'


class APIRequestError(Exception):
    """Исключение при ошибке запроса к API."""

    pass


def check_tokens():
    """Проверяет доступность переменных окружения."""
    missing_tokens_names = ', '.join(
        name for name in TOKEN_NAMES if not globals()[name]
    )
    if missing_tokens_names:
        message = MISSING_TOKENS_MESSAGE.format(missing_tokens_names)
        logging.critical(message)
        raise EnvironmentError(message)


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(BOT_SENT_MESSAGE_TEMPLATE.format(message))
        return True
    except Exception as error:
        logging.exception(SEND_MESSAGE_ERROR_TEMPLATE.format(error, message))
        return False


def get_api_answer(timestamp):
    """Делает запрос к API-сервису."""
    request_params = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': timestamp}
    )

    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise ConnectionError(
            REQUEST_ERROR_MESSAGE.format(error=error, **request_params)
        )

    if response.status_code != HTTPStatus.OK:
        raise APIRequestError(
            API_STATUS_CODE_ERROR.format(
                response.status_code,
                **request_params
            )
        )
    json_response = response.json()
    if 'code' in json_response or 'error' in json_response:
        error_key = 'code' if 'code' in json_response else 'error'
        raise APIRequestError(
            API_RESPONSE_ERROR.format(
                json_response.get(error_key),
                error_key,
                *request_params
            )
        )
    return json_response


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError(RESPONSE_NOT_DICT_MESSAGE.format(type(response)))
    if 'homeworks' not in response:  # Проверяем наличие ключа 'homeworks'
        raise KeyError(RESPONSE_MISSING_KEYS_MESSAGE)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            RESPONSE_HOMEWORKS_NOT_LIST_MESSAGE.format(
                type(homeworks)
            )
        )
    return homeworks


def parse_status(homework):
    """Извлекает статус из информации о домашней работе."""
    status = homework.get('status')
    if 'homework_name' not in homework:
        raise KeyError(MISSING_HOMEWORK_NAME_MESSAGE)
    if 'status' not in homework:
        raise KeyError(MISSING_HOMEWORK_STATUS_MESSAGE)
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(UNEXPECTED_HOMEWORK_STATUS_MESSAGE.format(status))
    return STATUS_CHANGED_MESSAGE.format(
        homework.get('homework_name'),
        HOMEWORK_VERDICTS.get(status)
    )


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                is_success = send_message(bot, parse_status(homeworks[0]))
                if is_success:
                    timestamp = response.get('current_date', timestamp)
                    last_error_message = None
            else:
                logging.debug(NO_NEW_UPDATES_MESSAGE)
        except Exception as error:
            error_message = REQUEST_ERROR_MESSAGE.format(error)
            logging.error(error_message)
            if error_message != last_error_message:
                send_message(bot, error_message)
                last_error_message = error_message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            os.path.join(os.path.dirname(__file__), 'bot.log'),
            maxBytes=100000,
            backupCount=5
        )
    ]
    logging.basicConfig(
        level=logging.DEBUG,
        format=formatter,
        handlers=handlers
    )
    main()
