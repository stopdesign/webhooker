import logging

from django.views.decorators.csrf import csrf_exempt

from main.ibkr_api_hook import webhook_call_view

log = logging.getLogger("main.views")


@csrf_exempt
def webhook_call(request, uid):
    return webhook_call_view(request, uid)
