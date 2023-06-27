import logging

from django.core.management.base import BaseCommand

from main.models import Webhook, WebhookCall

log = logging.getLogger("hook")


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-u", "--uid", dest="hook_uid")

    def handle(self, *args, **kwargs):
        hook_uid = kwargs["hook_uid"]

        try:
            webhook = Webhook.objects.get(uid=hook_uid)
        except Webhook.DoesNotExist:
            log.error(f"Hook {hook_uid} not found")
            return

        payload = '{"conid": 265598, "position": -3, "price": 188.12}'
        webhook_call = WebhookCall(
            webhook=webhook,
            method="TEST",
            request_headers='{"User-Agent": "manage.py"}',
            request_body=payload,
            response_body="{}",
            client_ip=None,
        )
        webhook_call.save()

        log.info(f"DONE")
