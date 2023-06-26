from django.db import models
from string import ascii_letters, digits
import secrets

alphabet = ascii_letters + digits

def hex_uuid():
    return ''.join(secrets.choice(alphabet) for _ in range(16))


class Webhook(models.Model):

    class Mode(models.TextChoices):
        ORDER = "ORDER", "Place order"
        PREVIEW = "PREVIEW", "Preview order"

    connection = models.ForeignKey("Connection", on_delete=models.CASCADE)
    uid = models.CharField(primary_key=True, default=hex_uuid, editable=False)

    mode = models.CharField(choices=Mode.choices, default=Mode.PREVIEW)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{uid}".format(**self.__dict__)
