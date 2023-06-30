import json
import logging

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from ipware import get_client_ip
from main.payloads import Order
from pydantic import ValidationError

from main.models import Webhook, WebhookCall

log = logging.getLogger("main.views")


def get_request_headers(request: HttpRequest) -> str:
    headers = {}
    for header, value in request.headers.items():
        headers[header] = value
    return json.dumps(headers, indent=2, default=str)


@csrf_exempt
def webhook_call(request, uid):
    if request.method != "POST":
        result = {"status": "error", "error": "method_not_allowed"}
        status_code = 405
        return JsonResponse(result, status=status_code)

    try:
        webhook = Webhook.objects.get(uid=uid)
    except Webhook.DoesNotExist:
        result = {"status": "error", "error": "hook_not_found"}
        status_code = 404
        return JsonResponse(result, status=status_code)

    # Предыдущее в базу не пишется, т.к. некуда и нет смысла.

    try:
        raw_payload = request.body.decode("utf-8")
    except Exception as e:
        log.exception(e)
        raw_payload = ""

    try:
        request_headers_str = get_request_headers(request)
    except Exception as e:
        log.exception(e)
        request_headers_str = None

    try:
        client_ip, _ = get_client_ip(request)
    except Exception as e:
        log.exception(e)
        client_ip = None

    # Валидация формата и полей запроса
    try:
        # TODO: Разделить валидаторы по разным webhook.mode
        Order.parse_raw(raw_payload)

        result = {"status": "ok", "mode": webhook.mode}
        status_code = 200

    except ValidationError as e:
        log.error(e)

        result = {
            "status": "error",
            "error": "payload_validation",
            "validation": json.loads(e.json()),
        }
        status_code = 400

    except Exception as e:
        log.exception(e)

        result = {"status": "error", "error": "payload_parsing"}
        status_code = 400

    try:
        # Создать WebhookCall и сохранить параметры вызова
        webhook_call = WebhookCall(
            webhook=webhook,
            method=request.method,
            request_headers=request_headers_str,
            request_body=raw_payload,
            response_body=json.dumps(result, default=str),
            client_ip=client_ip,
        )
        webhook_call.save()
        result["uid"] = webhook_call.uid

    except Exception as e:
        log.exception(e)
        result = {"status": "error", "error": "server_exception"}
        status_code = 500

    return JsonResponse(result, status=status_code)
