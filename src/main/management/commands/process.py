import logging
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand

from main.ibkr_api_hook import process_webhook_call
from main.models import WebhookCall

log = logging.getLogger("process")


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-rt", dest="reset_token", action="store_true")
        parser.add_argument("-a", "--all", dest="process_all", action="store_true")

    def handle(self, *args, **kwargs):
        process_all = kwargs["process_all"]
        reset_token = kwargs["reset_token"] or False

        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        too_late = now - timedelta(minutes=3)
        hooks = WebhookCall.objects.filter(
            timestamp__gte=too_late,
            success__isnull=True,
        ).order_by("timestamp")

        log.info(f"Hooks to process: {len(hooks)}")

        if not process_all:
            hooks = hooks[:1]

        for hook in hooks:
            log.info(f"Process: {hook}")
            process_webhook_call(hook, reset_token=reset_token)

        log.info(f"DONE")
