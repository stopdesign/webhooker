import logging
import re

import requests

from main.ibkr_api_session import log_api_call

log = logging.getLogger("alert")


ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class TgAlert:
    def __init__(self, config) -> None:
        self.token = config.get("token", "")
        self.channel_id = config.get("channel_id", 0)

    def message(self, text: str) -> requests.Response:
        if not (self.token and self.channel_id):
            raise ValueError("no token or channel_id")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {
            "text": ansi_escape.sub("", text),
            "chat_id": self.channel_id,
            "parse_mode": "html",
        }
        r = requests.post(url, data=data, timeout=2)

        if r.status_code != 200:
            raise requests.exceptions.HTTPError("post_text error")

        return r


class Result:
    response = None
    json = None

    def __init__(self, response, json=None) -> None:
        self.json = json
        self.response = response


def tg_alert(webhook_call):
    text = str(webhook_call.request_body)

    # FIXME: выпилить токен из кода
    # tamara local
    tg_token = "2040912183:AAHFqOyENpwf1oKKo7Ja9GocOQ21DD4NE5k"
    tg = TgAlert({"token": tg_token, "channel_id": 63082757})

    try:
        response = tg.message(text)
        # Токен в логах заменяется на ***
        response.url = str(response.url).replace(tg_token, "***")
        log_api_call(webhook_call, Result(response=response), "tg_message")
        webhook_call.success = True
    except Exception as e:
        log.error(f"Telegram error: {e}")
        log.exception(e)
        webhook_call.success = False

    webhook_call.save()
