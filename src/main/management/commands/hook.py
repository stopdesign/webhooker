import logging

from django.core.management.base import BaseCommand

from main.ibkr_api_hook import webhook_call_view

log = logging.getLogger("main.views")


class FakeRequest:
    def __init__(self) -> None:
        self.method = "POST"
        self.body = b'{"some": 123, "data": "paper"}'
        self.headers = {"REMOTE_ADDR": "127.0.0.1"}
        self.META = {"REMOTE_ADDR": "127.0.0.1"}


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-rt", dest="reset_token", action="store_true")
        parser.add_argument("-uid", "--uid", dest="hook_uid")

    def handle(self, *args, **kwargs):
        hook_uid = kwargs["hook_uid"]
        reset_token = kwargs["reset_token"] or False

        resp = webhook_call_view(FakeRequest(), hook_uid, reset_token=reset_token)

        log.info(f"DONE, code: {resp.status_code}")
        # print(resp.content.decode())
