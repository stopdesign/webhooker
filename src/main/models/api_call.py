from django.db import models


class APICall(models.Model):
    connection = models.ForeignKey("Connection", on_delete=models.CASCADE)
    webhook = models.ForeignKey("Webhook", on_delete=models.CASCADE, null=True)
    webhook_call = models.ForeignKey(
        "WebhookCall",
        on_delete=models.CASCADE,
        null=True,
        related_name="api_calls",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=30, blank=True, null=True)
    url = models.URLField()
    method = models.CharField(max_length=10)
    request_headers = models.TextField(blank=True, null=True)
    request_body = models.TextField(blank=True, null=True)
    response_status = models.PositiveIntegerField(blank=True, null=True)
    response_headers = models.TextField(blank=True, null=True)
    response_body = models.TextField(blank=True, null=True)
    duration = models.FloatField(null=True)

    @property
    def get_dt(self):
        return self.timestamp
