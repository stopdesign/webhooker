import logging
from datetime import datetime, timedelta, timezone
from time import sleep

from django.core.management.base import BaseCommand

from main.ibkr_api_hook import process_webhook_call
from main.models import WebhookCall
from main.telegram_hook import tg_alert

log = logging.getLogger("process")


class Command(BaseCommand):
    def process(self):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        too_late = now - timedelta(minutes=3)
        hooks = WebhookCall.objects.filter(
            timestamp__gte=too_late,
            success__isnull=True,
        ).order_by("timestamp")

        for hook in hooks:
            log.info(f"Process: {hook}, {hook.webhook.mode}")
            if hook.webhook.mode in ["PREVIEW", "ORDER"]:
                process_webhook_call(hook)
            else:
                tg_alert(hook)

    def handle(self, *args, **kwargs):
        while True:
            try:
                self.process()
                sleep(10)
            except KeyboardInterrupt:
                print()
                break
            except Exception as e:
                log.exception(e)
                sleep(30)

        log.info(f"DONE")
