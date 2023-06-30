import json
import logging
from random import randint
from time import sleep

from main.ibkr_api_session import ApiSession, log_api_call
from main.models import Webhook, WebhookCall
from main.payloads import Order

log = logging.getLogger("ibkr_api_hook")


def process_webhook_call(webhook_call, reset_token=False):
    webhook = webhook_call.webhook
    raw_payload = webhook_call.request_body

    webhook_call.success = False

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
            webhook_call.save()
            return

    # Получить account_uid, если его еще нет
    if not webhook.connection.account_uid:
        try:
            api.get_account_uid()
        except Exception as e:
            log.error(f"Account UID Exception: {e}")
            webhook_call.save()
            return

    # Пока всё ok
    log.error("AUTH DONE")

    # Дать авторизации настояться
    sleep(0.5)

    ####################################################
    # Парсинг и валидация параметров

    payload = Order.parse_raw(raw_payload)
    print("payload", payload)

    conid = payload.conid
    target_position = payload.position
    target_price = payload.price

    ####################################################
    # Полезные действия

    account = webhook.connection.account_uid

    log.warning(f"Account: {account}, mode: {webhook.mode}")

    # Invalidates the backend cache of the Portfolio
    res = api.ib.portfolio.invalidate_cache(account)
    log_api_call(webhook_call, res, "invalidate")

    sleep(0.5)

    # Позиции
    res = api.ib.portfolio.positions_simple(account)
    log_api_call(webhook_call, res, "positions")

    current_position = 0
    for pos in res.json:
        # print(pos)
        if pos.get("conid") == conid:
            current_position = int(pos.get("position"))
    print("POSITION:", current_position)

    # res = api.ib.accounts.accounts()
    # log_api_call(webhook_call, res, "accounts")
    # sleep(5)

    orders = None

    # Список ордеров
    for _ in range(3):
        res = api.ib.accounts.orders()
        log_api_call(webhook_call, res, "orders")
        if res.json and res.json.get("snapshot") == True:
            try:
                orders = res.json.get("orders", [])
            except Exception as e:
                log.exception(f"Order count error: {e}")
            break
        sleep(0.5)

    # Посчитать активные ордеры
    active_orders_cnt = 0
    for o in orders or []:
        if o.get("status") not in ["Inactive", "Cancelled"]:
            active_orders_cnt += 1
    if active_orders_cnt:
        log.error(f"Active orders: {active_orders_cnt}")

    # Отмена ордеров
    # for o in res.json["orders"]:
    #     o_id = o['orderId']
    #     log.error(f"Cancel order {o_id}")
    #     api.ib.accounts.cancel_order(account, o_id)

    print("ORDERS:")
    for i, o in enumerate(orders or []):
        print(f"{i+1}.", o["conid"], o["ticker"], o["orderDesc"], o["status"])

    # # ConID search
    # res = api.ib.trsrv.stocks("SPY")
    # log_api_call(webhook_call, res, "conid_search", verbose=True)

    # Что делать с активными ордерами по данному контракту?
    # - игнорировать
    # - отменить старые ордеры (сложно, долго)
    # - не создавать данный ордер

    # Варианты работы с позицией:
    # - передавать позицию и пытаться сделать такую
    # - передавать размер ордера

    order_amount = target_position - current_position
    side = None
    # limit_price = None
    if order_amount > 0:
        side = "BUY"
        # limit_price = round(target_price * 1.05, 2)
    if order_amount < 0:
        order_amount = abs(order_amount)
        side = "SELL"
        # limit_price = round(target_price * 0.95, 2)

    print("order amount", order_amount, side)

    order_data = {
        "conid": conid,
        "cOID": "test-%s" % randint(10000, 99999),
        "orderType": "MKT",
        "side": side,
        "tif": "GTC",
        # "price": limit_price,
        "quantity": order_amount,
        "outsideRTH": False,
        "useAdaptive": False,
    }
    print(json.dumps(order_data, indent=2, default=str))

    if side and order_amount > 0:
        # Preview Order
        if Webhook.Mode.PREVIEW == webhook.mode:
            res = api.ib.accounts.preview_order(account, order_data, confirm=True)
            log_api_call(webhook_call, res, "what_if")
            if res and res.json and type(res.json) is dict:
                if "position" in res.json:
                    webhook_call.success = True
                if res.json.get("error"):
                    log.error(f"Preview order error: {res.json['error']}")

        # Place Order
        if Webhook.Mode.ORDER == webhook.mode:
            ress = api.ib.accounts.place_order(account, order_data, confirm=True)
            for res in ress:
                log_api_call(webhook_call, res, "new_order", verbose=True)
                if res and res.json and type(res.json) is list:
                    o_res = res.json[0]
                    if type(o_res) is dict and o_res.get("order_id"):
                        webhook_call.success = True
    else:
        log.warning("No changes in position")
        webhook_call.success = True

    # # Разлогин (для тестов)
    # res = api.ib.iserver.portal_logout()
    # log_api_call(webhook_call, res, "portal_logout")

    webhook_call.save()
