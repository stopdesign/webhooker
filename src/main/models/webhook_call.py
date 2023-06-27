import uuid

from django.db import models


def hex_uuid():
    return uuid.uuid4().hex


class WebhookCall(models.Model):
    uid = models.UUIDField(primary_key=True, default=hex_uuid, editable=False)
    webhook = models.ForeignKey("Webhook", on_delete=models.CASCADE)

    client_ip = models.GenericIPAddressField(null=True, blank=True)
    method = models.CharField(max_length=10)
    request_headers = models.TextField(blank=True, null=True)
    request_body = models.TextField(blank=True, null=True)
    response_body = models.TextField(blank=True, null=True)

    success = models.BooleanField(null=True, default=None)

    # status = models.CharField(max_length=10)  # new, working, ok, fail...
    # errors = models.CharField()  # что пошло не так

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{uid}".format(**self.__dict__)
