from dataclasses import dataclass
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from main.models import Webhook, WebhookCall, Connection, APICall
from main.ibkr_oauth import IbkrOAuth

import json
import logging
from pprint import pprint
from datetime import datetime, timezone
from random import randint
from time import sleep
from ipware import get_client_ip
from ibkr_web_api import OAuthIBClient
from django.http import HttpRequest


log = logging.getLogger("main.views")



def get_request_headers(request: HttpRequest) -> dict:
    headers = {}
    for header, value in request.headers.items():
        headers[header] = value
    return headers


def log_api_call(call, res, name=None, verbose=False):
    if verbose:
        dump = json.dumps(res.json, indent=2, default=str)
        log.info(f"API call: {name}, json: {dump}")
    else:
        log.info(f"API call: {name}, {res}")

    webhook = call.webhook
    request = res.response.request

    api_call = APICall(
        connection=webhook.connection,
        webhook=webhook,
        webhook_call=call,
        name=name,
        url=res.response.url,
        method=request.method,
        request_headers=request.headers,
        request_body=request.body.decode() if request.body else request.body,
        response_status=res.response.status_code,
        response_headers=res.response.headers,
        response_body=res.response.text,
        duration=res.response.elapsed.total_seconds(),
    )
    api_call.save()


class Result:
    response = None
    json = None

    def __init__(self, response, json=None) -> None:
        self.json = json
        self.response = response


class ApiSession:

    def __init__(self, webhook_call: WebhookCall) -> None:

        self.webhook_call: WebhookCall = webhook_call
        self.webhook: Webhook = self.webhook_call.webhook
        self.connection: Connection = self.webhook.connection

        self.ib = OAuthIBClient(
            consumer_key=self.connection.oauth_consumer_key,
            oauth_access_token=self.connection.oauth_token,
            live_session_token=self.connection.live_session_token,
        )

    def refresh_live_token(self):
        ibanina = IbkrOAuth(
            self.connection.oauth_consumer_key,
            self.connection.oauth_token,
            self.connection.oauth_token_secret,
            self.connection.dh_params,
            self.connection.signature_key,
            self.connection.encryption_key,
        )

        try:
            token, token_exp = ibanina.obtain_live_session_token()
            token_exp = token_exp.replace(tzinfo=timezone.utc)

            res = Result(response=ibanina.last_request_result)
            log_api_call(self.webhook_call, res, "live_token")

            self.connection.live_session_token = token
            self.connection.live_session_token_expiration = token_exp
            self.connection.save()

            self.need_portal_init = True
            return True

        except Exception as e:
            log.exception(e)
            print("Error obtaining live session token")
            return False

    def session_init(self):
        # Этот запрос нельзя делать много раз подряд
        # Буквально за 5-10 попыток прилетал {'wait': True}

        res = self.ib._session.auth_request()
        log_api_call(self.webhook_call, res, "iserver", verbose=True)
        if res.json and res.json["authenticated"] and res.json["connected"]:
            self.need_portal_init = False
            return True
        else:
            self.need_portal_init = True
            raise Exception("Error session init")

    def portal_init(self):

        print("portal init, token:", self.connection.live_session_token)

        res = self.ib._session.init_portal_session()
        log_api_call(self.webhook_call, res, "portal", verbose=True)
        if res.json and res.json["success"]:
            self.need_portal_init = False
            return True
        else:
            self.need_portal_init = True
            raise Exception("Error portal init")

    def on_invalid_signature(self):
        self.need_portal_init = True
        return self.portal_init() and self.session_init()

    def has_valid_lst(self):
        if not self.connection.live_session_token:
            return False
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        exp = self.connection.live_session_token_expiration
        return exp and (exp - now).total_seconds() > 23 * 3600

    def check_auth_status(self):
        res = self.ib.iserver.auth_status()
        log_api_call(self.webhook_call, res, "auth_status", verbose=True)
        return res.json and res.json["authenticated"] and res.json["connected"]

    def auth_procedure(self):
        if self.has_valid_lst():
            return self.check_auth_status() or self.session_init()
        else:
            if self.refresh_live_token():
                sleep(2)
                return self.portal_init() and self.session_init()
            else:
                raise Exception("Error live token")

    def check_and_update_auth(self):

        # Попытка залогиниться
        for i in range(3):
            sleep(1)
            log.info(f"\nATTEMPT: {i+1}")
            try:
                if self.auth_procedure():
                    break
            except Exception as e:
                log.error(f"Auth exception: {e}")
        else:
            raise Exception("too many fails")


@csrf_exempt
def webhook_call(request, uid):
    # идеи: добавить необязательное поле "nonce"

    print("\n\n================================")
    print("webhook_call", uid)

    try:
        webhook = Webhook.objects.get(uid=uid)
    except Webhook.DoesNotExist:
        return JsonResponse({"status": "404"}, status=404)

    client_ip, _ = get_client_ip(request)

    # Сохранить вызов в базу
    payload = request.body.decode("utf-8")

    request_headers = get_request_headers(request)
    request_headers_str = json.dumps(request_headers, indent=2, default=str)

    webhook_call = WebhookCall(
        webhook=webhook,
        method=request.method,
        request_headers=request_headers_str,
        request_body=payload,
        client_ip=client_ip,
    )
    webhook_call.save()

    api = ApiSession(webhook_call)

    connected = False

    try:
        api.check_and_update_auth()
        status_code = 200  # ???
        connected = True
    except Exception as e:
        result = {"status": "error", "error": "processing", "exception": str(e)}
        status_code = 400

    # Получить account_uid, если его еще нет
    if connected and not webhook.connection.account_uid:
        res = api.ib.accounts.accounts()

        # Вытащить account_uid
        if res.json and res.json["selectedAccount"]:
            webhook.connection.account_uid = res.json["selectedAccount"]
            webhook.connection.paper = res.json["isPaper"]
            webhook.connection.save()

    # Пока всё ok
    result = {"status": "ok", "order": None}

    # Тестовый ордер
    if connected and webhook.connection.account_uid:

        account_uid = webhook.connection.account_uid

        # Позиции
        res = api.ib.portfolio.positions_simple(account_uid)
        log_api_call(webhook_call, res, "positions")

        # Список ордеров
        for _ in range(3):
            res = api.ib.accounts.orders()
            log_api_call(webhook_call, res, "orders")
            if res.json and res.json.get("snapshot") == True:
                break
            sleep(0.5)

        order_data = {
            "conid": 265598,
            "cOID": "test-%s" % randint(10000, 99999),
            "orderType": "LMT",
            "price": 180,
            "side": "BUY",
            "tif": "GTC",
            "quantity": 1,
            "outsideRTH": True,
            "useAdaptive": False,
        }
        res = api.ib.accounts.preview_order(account_uid, order_data, confirm=True)
        log_api_call(webhook_call, res, "what_if")

        # ress = api.ib.accounts.place_order(account_uid, order_data, confirm=True)
        # for res in ress:
        #     log_api_call(webhook_call, res, "new_order")

        # if res.json:
        #     result["order"] = {
        #         "account_uid": account_uid,
        #         "position": res.json.get("position"),
        #         "error": res.json.get("error"),
        #     }

    webhook_call.response_body = json.dumps(result, default=str)
    webhook_call.save()

    return JsonResponse(result, status=status_code)
