import logging
import os
import time

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


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    missing_tokens = [token for token in tokens if not token]
    if missing_tokens:
        logging.critical(
            f"Отсутствуют обязательные переменные окружения: {missing_tokens}"
        )
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(f'Бот отправил сообщение: "{message}"')
    except Exception as error:
        logging.error(f"Сбой при отправке сообщения: {error}")


def get_api_answer(timestamp):
    """Делает запрос к API-сервису."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        if response.status_code != 200:
            raise TypeError(f'Код ответа API: {response.status_code}')
        return response.json()
    except requests.RequestException as error:
        logging.error(f'Сбой в работе программы: {error}')


def check_response(response):
    """Проверяет ответ API на корректность."""
    expected_keys = ['homeworks', 'current_date']
    if not all(key in response for key in expected_keys):
        logging.error(f"Отсутствуют ожидаемые ключи в ответе API: {response}")
        raise TypeError("Некорректный ответ API")
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        logging.error("Некорректный формат данных домашних работ в ответе API")
        raise TypeError("Некорректный формат данных домашних работ")
    return homeworks


def parse_status(homework):
    """Извлекает статус из информации о домашней работе."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_name is None or homework_status is None:
        logging.error(
            f"Отсутствуют данные о названии или статусе работы: {homework}"
        )
        raise Exception("Неполные данные о домашней работе")
    verdict = HOMEWORK_VERDICTS.get(homework_status)
    if verdict is None:
        logging.error(f"Неожиданный статус работы: {homework_status}")
        raise Exception(
            f"Неизвестный статус домашней работы: {homework['status']}"
        )
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        exit(1)
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                send_message(bot, parse_status(homeworks[0]))
                timestamp = response.get('current_date')
            else:
                logging.debug('Нет новых обновлений')

            time.sleep(RETRY_PERIOD)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            send_message(bot, message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
