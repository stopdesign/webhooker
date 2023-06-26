import json
import logging
from random import randint
from time import sleep

from django.http import HttpRequest, JsonResponse
from ipware import get_client_ip

from main.ibkr_api_session import ApiSession, log_api_call
from main.models import Webhook, WebhookCall

log = logging.getLogger("ibkr_api_hook")


def get_request_headers(request: HttpRequest) -> dict:
    headers = {}
    for header, value in request.headers.items():
        headers[header] = value
    return headers


def webhook_call_view(request, uid, reset_token=False):
    # идеи: добавить необязательное поле "nonce"

    log.info("=============== WEBHOOK =================")
    log.info(f"Webhook_call, {uid}")

    try:
        webhook = Webhook.objects.get(uid=uid)
    except Webhook.DoesNotExist:
        return JsonResponse({"status": "404"}, status=404)

    ####################################################
    # Создать WebhookCall и сохранить там параметры вызова

    payload = request.body.decode("utf-8")

    request_headers = get_request_headers(request)
    request_headers_str = json.dumps(request_headers, indent=2, default=str)

    client_ip, _ = get_client_ip(request)

    webhook_call = WebhookCall(
        webhook=webhook,
        method=request.method,
        request_headers=request_headers_str,
        request_body=payload,
        client_ip=client_ip,
    )
    webhook_call.save()

    ####################################################
    # Авторизация

    api = ApiSession(webhook_call)

    # Сбросить токен
    if reset_token:
        api.reset_token()

    # Шаги аутентификации
    if not api.iserver_session:
        try:
            api.auth_machine()
        except Exception as e:
            log.error(f"Auth Machine Exception: {e}")
            result = {"status": "error", "exception": str(e)}
            return JsonResponse(result, status=400)

    # Получить account_uid, если его еще нет
    if not webhook.connection.account_uid:
        try:
            api.get_account_uid()
        except Exception as e:
            log.error(f"Account UID Exception: {e}")
            result = {"status": "error", "exception": str(e)}
            return JsonResponse(result, status=400)

    # Пока всё ok
    log.error("AUTH DONE")

    # Дать авторизации настояться
    sleep(0.5)

    ####################################################
    # Тестовый ордер и другие полезные действия

    account = webhook.connection.account_uid

    log.warning(f"Account: {account}, mode: {webhook.mode}")

    # Invalidates the backend cache of the Portfolio
    res = api.ib.portfolio.invalidate_cache(account)
    log_api_call(webhook_call, res, "invalidate")

    sleep(0.5)

    # Позиции
    res = api.ib.portfolio.positions_simple(account)
    log_api_call(webhook_call, res, "positions")

    # Список ордеров
    for _ in range(3):
        res = api.ib.accounts.orders()
        log_api_call(webhook_call, res, "orders")
        if res.json and res.json.get("snapshot") == True:
            try:
                active_orders_cnt = 0
                for o in res.json.get("orders", []):
                    if o.get("status") not in ["Inactive", "Cancelled"]:
                        active_orders_cnt += 1
                if active_orders_cnt:
                    log.error(f"Active orders count: {active_orders_cnt}")
            except Exception as e:
                log.exception(f"Order count error: {e}")
            # Отмена ордеров
            # for o in res.json["orders"]:
            #     log.error(f"Cancel order {o['orderId']}")
            #     api.ib.accounts.cancel_order(account, o["orderId"])
            break
        sleep(0.5)

    # ConID search
    # res = api.ib.trsrv.stocks("AAPL,TSLA,MSFT,NFLX,SPY")
    # log_api_call(webhook_call, res, "conid_search", verbose=True)

    order_data = {
        "conid": 265598,
        "cOID": "test-%s" % randint(10000, 99999),
        "orderType": "LMT",
        "price": 100,
        "side": "BUY",
        "tif": "GTC",
        "quantity": 1,
        "outsideRTH": True,
        "useAdaptive": False,
    }

    # Из позиций и payload посчитать amount для ордера.
    # Если

    # Preview Order
    if Webhook.Mode.PREVIEW == webhook.mode:
        webhook_call.success = False
        res = api.ib.accounts.preview_order(account, order_data, confirm=True)
        log_api_call(webhook_call, res, "what_if")
        if res and res.json and type(res.json) is dict:
            if "position" in res.json:
                webhook_call.success = True
            if res.json.get("error"):
                webhook_call.success = False
                log.error(f"Preview order error: {res.json['error']}")

    # Place Order
    if Webhook.Mode.ORDER == webhook.mode:
        webhook_call.success = False
        ress = api.ib.accounts.place_order(account, order_data, confirm=True)
        for res in ress:
            log_api_call(webhook_call, res, "new_order", verbose=True)
            if res and res.json and type(res.json) is list:
                o_res = res.json[0]
                if type(o_res) is dict and o_res.get("order_id"):
                    webhook_call.success = True

    # Разлогин (для тестов)
    res = api.ib.iserver.portal_logout()
    log_api_call(webhook_call, res, "portal_logout")

    result = {"status": "ok", "mode": webhook.mode}
    status_code = 200

    webhook_call.response_body = json.dumps(result, default=str)
    webhook_call.save()

    return JsonResponse(result, status=status_code)
