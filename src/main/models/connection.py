from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings


class Connection(models.Model):

    class Broker(models.TextChoices):
        IBKR = "IBKR", "Interactive Brokers"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    broker = models.CharField(choices=Broker.choices, default=Broker.IBKR)

    name = models.CharField(null=False, default="")

    # OAuth-параметры
    oauth_consumer_key = models.CharField(null=False, default="")
    oauth_token = models.CharField(null=False, default="")
    oauth_token_secret = models.TextField(null=False, default="")

    # Криптография
    dh_params = models.TextField(null=False, default="")
    signature_key = models.TextField(null=False, default="")
    encryption_key = models.TextField(null=False, default="")

    # Добывается при подключении брокера, регулярно обновляется
    live_session_token = models.CharField(null=False, default="", blank=True)
    live_session_token_expiration = models.DateTimeField(null=True, blank=True)

    # Добывается после получения live_session_token
    user_uid = models.CharField(null=False, blank=True, default="")
    account_uid = models.CharField(null=False, blank=True, default="")
    paper = models.BooleanField(default=False)

    last_success = models.DateTimeField(null=True, editable=False)

    enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{id} | {oauth_consumer_key} | {name}".format(**self.__dict__)
