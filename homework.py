import logging
import os
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler
from unittest import TestCase
from unittest import main as uni_main
from unittest import mock

import requests
from dotenv import load_dotenv
from requests import HTTPError
from telebot import TeleBot


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


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
    '(ожидается список, получено {}): {}'
)
MISSING_HOMEWORK_NAME_MESSAGE = 'Отсутствует название домашней работы: {}'
MISSING_HOMEWORK_STATUS_MESSAGE = 'Отсутствует статус домашней работы: {}'
UNEXPECTED_HOMEWORK_STATUS_MESSAGE = 'Неожиданный статус работы: {}'
NO_NEW_UPDATES_MESSAGE = 'Нет новых обновлений'
NETWORK_ERROR_MESSAGE = "Сетевая ошибка"


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    missing_tokens = [token for token in tokens if not token]
    if missing_tokens:
        logging.critical(
            MISSING_TOKENS_MESSAGE.format(missing_tokens)
        )
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(BOT_SENT_MESSAGE_TEMPLATE.format(message))
    except Exception as error:
        logging.exception(SEND_MESSAGE_ERROR_TEMPLATE.format(error))


def get_api_answer(timestamp):
    """Делает запрос к API-сервису."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        raise RuntimeError(REQUEST_ERROR_MESSAGE.format(error))
    if response.status_code != HTTPStatus.OK:
        raise HTTPError(
            API_STATUS_CODE_ERROR.format(
                response.status_code,
                ENDPOINT,
                HEADERS,
                {'from_date': timestamp}
            )
        )
    json_response = response.json()
    if 'code' in json_response or 'error' in json_response:
        raise HTTPError(
            API_RESPONSE_ERROR.format(
                json_response.get('code'), json_response.get('error')
            )
        )
    return json_response


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError(RESPONSE_NOT_DICT_MESSAGE.format(response))
    expected_keys = {'homeworks'}
    if not expected_keys.issubset(response):
        raise ValueError(RESPONSE_MISSING_KEYS_MESSAGE.format(response))
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            RESPONSE_HOMEWORKS_NOT_LIST_MESSAGE.format(
                type(homeworks),
                homeworks
            )
        )
    return homeworks


def parse_status(homework):
    """Извлекает статус из информации о домашней работе."""
    name = homework.get('homework_name')
    status = homework.get('status')
    if 'homework_name' not in homework:
        raise TypeError(MISSING_HOMEWORK_NAME_MESSAGE.format(homework))
    if 'status' not in homework:
        raise TypeError(MISSING_HOMEWORK_STATUS_MESSAGE.format(homework))
    if status not in HOMEWORK_VERDICTS:
        raise TypeError(UNEXPECTED_HOMEWORK_STATUS_MESSAGE.format(status))
    verdict = HOMEWORK_VERDICTS.get(status)
    return f'Изменился статус проверки работы "{name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        return
    log_file = os.path.join(os.path.dirname(__file__), 'bot.log')
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(log_file, maxBytes=100000, backupCount=5)
    ]
    logging.basicConfig(
        level=logging.DEBUG,
        format=formatter,
        handlers=handlers
    )
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                send_message(bot, parse_status(homeworks[0]))
                timestamp = response.get('current_date', timestamp)
            else:
                logging.debug(NO_NEW_UPDATES_MESSAGE)
        except Exception as error:
            message = REQUEST_ERROR_MESSAGE.format(error)
            logging.error(message)
            send_message(bot, message)
        time.sleep(RETRY_PERIOD)


class TestNetworkError(TestCase):
    """Проверка обработки ошибки соединения с сетью."""

    @mock.patch('requests.get')
    def test_network_error(self, mock_get):
        mock_get.side_effect = requests.RequestException(NETWORK_ERROR_MESSAGE)
        main()


class TestServerError(TestCase):
    """Проверка обработки ошибки сервера."""

    @mock.patch('requests.get')
    def test_server_error(self, mock_get):
        mock_response = mock.Mock()
        mock_response.json.return_value = {'error': 'Ошибка сервера'}
        mock_get.return_value = mock_response
        main()


class TestUnexpectedStatusCode(TestCase):
    """Проверка обработки ошибки неожиданного статуса."""

    @mock.patch('requests.get')
    def test_unexpected_status_code(self, mock_get):
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        main()


class TestUnexpectedHomeworkStatus(TestCase):
    @mock.patch('requests.get')
    def test_unexpected_homework_status(self, mock_get):
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            'homeworks': [{'homework_name': 'hw1', 'status': 'unknown'}]
        }
        mock_get.return_value = mock_response
        main()


class TestInvalidJson(TestCase):
    """Проверка обработки ошибки неожиданного статуса ДЗ."""

    @mock.patch('requests.get')
    def test_invalid_json(self, mock_get):
        mock_response = mock.Mock()
        mock_response.json.return_value = {'homeworks': 1}
        mock_get.return_value = mock_response
        main()


if __name__ == '__main__':
    uni_main()
