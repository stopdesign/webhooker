import json
import logging
from django.core.management.base import BaseCommand
from django.http import JsonResponse
from main.models import Webhook, WebhookCall, Connection
from main.ibkr_oauth import IbkrOAuth
from datetime import datetime, timezone
from random import randint
from time import sleep
from ipware import get_client_ip
from ibkr_web_api import OAuthIBClient
from main.views import log_api_call, get_request_headers


log = logging.getLogger("main.views")


class Result:
    response = None
    json = None

    def __init__(self, response, json=None) -> None:
        self.json = json
        self.response = response


class SignatureError(Exception):
    pass


class WaitError(Exception):
    pass


class IserverInitError(Exception):
    pass


def raise_on_wait(res):
    if res and res.json and "wait" in res.json:
        raise WaitError


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

        self.valid_live_session_token = self._has_valid_lst()
        self.portal_session = None
        self.iserver_session = None  # можно проверить

        # TODO: приделать время к проверке состояния
        # Состояния:
        #   - live session token     exp 24 h
        #   - portal session         exp 20 min ?
        #   - iserver session        exp  1 min

        # Терминальные ошибки:
        #   - не получен токен (плохой аккаунт, бан за попытки)
        #   - wait (бан за попытки)
        #   - IBKR закрыт на обед или отвечает хуйню
        #   - не сработал session_init и есть конкретная ошибка
        #   - не сработал portal_init для свежего токена

    def refresh_live_token(self):
        """
        Получение нового LST.
        """
        log.warning(f"Current token: {self.connection.live_session_token}")
        log.warning(
            f"Token expiration: {self.connection.live_session_token_expiration}"
        )
        log.warning(f"Refresh token")

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

            self.valid_live_session_token = True
            self.portal_session = False

            return True

        except Exception as e:
            self.valid_live_session_token = False
            self.portal_session = False

            log.error("Error obtaining live session token")
            raise e

    def portal_session_init(self):
        """
        Активация portal session.
        """
        log.warning(f"Portal init, token: {self.connection.live_session_token}")

        res = self.ib._session.init_portal_session()
        log_api_call(self.webhook_call, res, "portal")

        raise_on_wait(res)

        if res.json and (res.json.get("success") or "set" in res.json.get("message")):
            self.portal_session = True
        else:
            log.error(f"portal_session_init: {res}")
            raise Exception("portal_session_init")

    def iserver_session_init(self):
        """
        Активация iserver session.

        Этот запрос нельзя делать много раз подряд
        Буквально за 5-10 попыток прилетал {'wait': True}

        Может отвечать статусом 200, но без authenticated.
        {'passed': False, 'authenticated': False, 'connected': True, 'competing': False}

        Может вернуть статус 503 и {"error":"unknown"}.
        """
        log.warning(f"Iserver session init")

        res = self.ib._session.auth_request()
        log_api_call(self.webhook_call, res, "iserver")

        raise_on_wait(res)

        if res.json and res.json["authenticated"] and res.json["connected"]:
            self.iserver_session = True
        else:
            log.error(f"iserver_session_init: {res}")
            raise IserverInitError()

    def get_account_uid(self):
        log.warning(f"Get account_uid")

        res = self.ib.accounts.accounts()
        log_api_call(self.webhook_call, res, "accounts")
        if res.json and res.json.get("selectedAccount"):
            self.connection.account_uid = res.json["selectedAccount"]
            self.connection.paper = res.json["isPaper"]
            self.connection.save()
            return True
        else:
            log.error(f"no account uid: {res}")
            raise Exception("no account uid")

    def reset_token(self):
        log.error("RESET TOKEN")
        now = datetime.now().replace(tzinfo=timezone.utc)
        self.valid_live_session_token = False
        self.portal_session = False
        self.connection.live_session_token = ""
        self.connection.live_session_token_expiration = now
        self.connection.save()

    # def on_invalid_signature(self):
    #     return self.portal_init() and self.session_init()

    def _has_valid_lst(self):
        if not self.connection.live_session_token:
            return False
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        exp = self.connection.live_session_token_expiration
        return exp and (exp - now).total_seconds() > 3600

    def _check_auth_status(self):
        log.warning(f"Check iserver auth status")
        res = self.ib.iserver.auth_status()
        log_api_call(self.webhook_call, res, "auth_status")
        self.iserver_session = (
            res.json and res.json.get("authenticated") and res.json.get("connected")
        )
        return self.iserver_session

    def auth_machine(self):
        # В норме всё должно произойти с первого захода,
        # но есть условно нормальные сценарии, которые требуют повтора.
        for i in range(3):
            self.iserver_session = False

            if i:
                print("Wait 5 sec...")
                sleep(5)

            try:
                if self.valid_live_session_token and self._check_auth_status():
                    break

                if not self.valid_live_session_token:
                    self.refresh_live_token()

                if not self.portal_session:
                    self.portal_session_init()

                if not self.iserver_session:
                    self.iserver_session_init()

            except SignatureError as e:
                log.error(f"Auth Error: {e}")
                self.portal_session = False
                continue

            except IserverInitError:
                # Подождать и повторить.
                pass

            except WaitError:
                raise

            except Exception as e:
                log.error(f"Auth Error: {e}")
                log.exception(e)

            if self.iserver_session:
                break

        else:
            raise Exception("auth loop")

        return True


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
            result = {"status": "error", "error": "auth_machine", "exception": str(e)}
            return JsonResponse(result, status=400)

    # Получить account_uid, если его еще нет
    if not webhook.connection.account_uid:
        try:
            api.get_account_uid()
        except Exception as e:
            log.error(f"Account UID Exception: {e}")
            result = {"status": "error", "error": "account_uid", "exception": str(e)}
            return JsonResponse(result, status=400)

    # Пока всё ok
    log.error("AUTH DONE")

    # Дать авторизации настояться
    sleep(0.5)

    ####################################################
    # Тестовый ордер и другие полезные действия

    account_uid = webhook.connection.account_uid

    log.warning(f"Account: {account_uid}, mode: {webhook.mode}")

    # Invalidates the backend cache of the Portfolio
    res = api.ib.portfolio.invalidate_cache(account_uid)
    log_api_call(webhook_call, res, "invalidate")

    sleep(0.5)

    # Позиции
    res = api.ib.portfolio.positions_simple(account_uid)
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
            #     api.ib.accounts.cancel_order(account_uid, o["orderId"])
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
        res = api.ib.accounts.preview_order(account_uid, order_data, confirm=True)
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
        ress = api.ib.accounts.place_order(account_uid, order_data, confirm=True)
        for res in ress:
            log_api_call(webhook_call, res, "new_order", verbose=True)
            if res and res.json and type(res.json) is list:
                o_res = res.json[0]
                if type(o_res) is dict and o_res.get("order_id"):
                    webhook_call.success = True

    result = {"status": "ok", "mode": webhook.mode}
    status_code = 200

    webhook_call.response_body = json.dumps(result, default=str)
    webhook_call.save()

    return JsonResponse(result, status=status_code)


class FakeRequest:
    def __init__(self) -> None:
        self.method = "POST"
        self.body = b'{"some": 123, "data": "paper"}'
        self.headers = {"REMOTE_ADDR": "127.0.0.1"}
        self.META = {"REMOTE_ADDR": "127.0.0.1"}


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-rt", dest="reset_token", action="store_true")
        parser.add_argument("-uid", "--uid", dest="hook_uid")

    def handle(self, *args, **kwargs):
        hook_uid = kwargs["hook_uid"]
        reset_token = kwargs["reset_token"] or False

        resp = webhook_call_view(FakeRequest(), hook_uid, reset_token=reset_token)

        log.info(f"DONE, code: {resp.status_code}")
        # print(resp.content.decode())
