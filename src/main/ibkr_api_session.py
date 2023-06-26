import json
import logging
from datetime import datetime, timezone
from time import monotonic, sleep

from ibkr_web_api import OAuthIBClient

from main.ibkr_oauth import IbkrOAuth
from main.models import APICall, Connection, Webhook, WebhookCall

log = logging.getLogger("ibkr_api_session")


class SignatureError(Exception):
    pass


class WaitError(Exception):
    pass


class IserverInitError(Exception):
    pass


class PortalInitError(Exception):
    pass


class Result:
    response = None
    json = None

    def __init__(self, response, json=None) -> None:
        self.json = json
        self.response = response


def raise_on_wait(res):
    if res and res.json and "wait" in res.json:
        raise WaitError


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

        self.live_session_refreshed_at = 0

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

            self.live_session_refreshed_at = monotonic()

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

        for i in range(5):
            if i:
                sleep(5)

            res = self.ib._session.init_portal_session()
            log_api_call(self.webhook_call, res, "portal")

            raise_on_wait(res)

            if res.json and (
                res.json.get("success") or "set" in res.json.get("message")
            ):
                self.portal_session = True
                return

            # Если live_session_token получен не сейчас, то идти за новым
            if monotonic() - self.live_session_refreshed_at > 60:
                raise PortalInitError("Revoked token?")

        raise PortalInitError("Fail after many attempts")

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

            except PortalInitError as e:
                log.error(f"Token Error: {e}")
                self.valid_live_session_token = False
                self.portal_session = False
                self.iserver_session = False
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
