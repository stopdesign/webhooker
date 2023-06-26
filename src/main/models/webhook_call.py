from django.db import models
import uuid


def hex_uuid():
    return uuid.uuid4().hex


class WebhookCall(models.Model):
    uid = models.UUIDField(primary_key=True, default=hex_uuid, editable=False)
    webhook = models.ForeignKey("Webhook", on_delete=models.CASCADE)

    client_ip = models.GenericIPAddressField()
    method = models.CharField(max_length=10)
    request_headers = models.TextField(blank=True, null=True)
    request_body = models.TextField(blank=True, null=True)
    response_body = models.TextField(blank=True, null=True)

    # auth_success = models.BooleanField(null=True, default=None)
    success = models.BooleanField(null=True, default=None)

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{uid}".format(**self.__dict__)
