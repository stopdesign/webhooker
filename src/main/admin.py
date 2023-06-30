import json

from django.contrib import admin
from django.db.models import Count
from django.forms import TextInput, widgets
from django.utils.safestring import mark_safe

from project.admin import admin_site
from project.helpers.admin_decorators import allow_tags, boolean, short_description

from .models import APICall, Connection, Webhook, WebhookCall


class PrettyJSONWidget(widgets.Textarea):
    def format_value(self, value):
        try:
            value = json.dumps(json.loads(value), indent=4, ensure_ascii=False)
            # these lines will try to adjust size of TextArea to fit to content
            row_lengths = [len(r) for r in value.split("\n")]
            self.attrs["rows"] = min(max(len(row_lengths) + 2, 3), 25)
            self.attrs["cols"] = min(max(max(row_lengths) + 2, 75), 100)
            self.attrs["style"] = "font-family: monospace"
            self.attrs["spellcheck"] = "false"
            return value
        except Exception as e:
            # logger.warning("Error while formatting JSON: {}".format(e))
            return super(PrettyJSONWidget, self).format_value(value)


def color_code(code, text=None) -> str:
    msg = f"{text}" if text else str(code)
    if code in [200, 201]:
        return f"<span style='color: #070'>{msg}</span>"
    if code >= 400:
        return f"<span style='color: #d00'>{msg}</span>"
    return f"<span>{msg}</span>"


@admin.register(Connection, site=admin_site)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "name",
        "broker",
        "oauth_consumer_key",
        "oauth_token",
        "live_session_token",
        "live_session_token_expiration",
        "paper",
        "enabled",
        "updated_at",
    )
    readonly_fields = ("user", "user_uid", "account_uid", "paper")
    actions_on_top = False
    actions = None

    def save_model(self, request, obj, form, change):
        obj.user = request.user
        obj.save()


@admin.register(Webhook, site=admin_site)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ("uid", "connection", "mode", "call_count", "created_at")
    list_per_page = 25
    list_max_show_all = 1000
    actions_on_top = False
    actions = None

    def call_count(self, obj):
        return obj.call_count

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(call_count=Count("webhookcall"))
        return queryset


modal_tmpl = """
  <div class="modal micromodal-slide" id="{id}" aria-hidden="true">
    <div class="modal__overlay" tabindex="-1">
      <div class="modal__overlay_close" data-micromodal-close></div>
      <div class="modal__container" role="dialog" aria-modal="true" aria-labelledby="{id}-title">
        <header class="modal__header">
          <div class="modal__title" id="{id}-title">{title}</div>
          <button class="modal__close" aria-label="Close modal" data-micromodal-close></button>
        </header>
        <main class="modal__content" id="{id}-content">{content}</main>
      </div>
    </div>
  </div>
"""


class APICallInline(admin.TabularInline):
    model = APICall
    fields = (
        "timestamp",
        "name",
        "method",
        "url",
        "status",
        "time",
        "response",
    )
    readonly_fields = ["timestamp", "status", "time", "response"]
    ordering = ["timestamp"]
    extra = 0

    @allow_tags
    def response(self, obj):
        value = obj.response_body
        if value:
            truncated_value = value[:150]
            title = "Response body"
            try:
                value = json.dumps(json.loads(value), indent=2)
            except:
                pass
            value = "<pre>%s</pre>" % value[:5000]
            modal_html = modal_tmpl.format(id=obj.pk, content=value, title=title)
            return mark_safe(
                f"<span class='micromodal-trigger' "
                f" data-micromodal-trigger='{obj.pk}' "
                f">{truncated_value}</span>{modal_html}"
            )
        else:
            return ""

    def time(self, obj):
        if obj.duration is not None:
            return "{0:0.3f}".format(round(obj.duration, 3))

    @allow_tags
    def status(self, obj):
        return color_code(obj.response_status)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WebhookCall, site=admin_site)
class WebhookCallAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "webhook",
        "connection",
        "mode_",
        "success_",
        "api_statuses",
        # "request_body",
    )
    readonly_fields = (
        # "uid",
        "timestamp",
        "client_ip",
        "method",
        "webhook",
        "request_body",
        "response_body",
    )
    exclude = ("request_headers",)
    ordering = ["-timestamp"]
    inlines = [APICallInline]
    list_per_page = 30
    list_max_show_all = 1000
    actions_on_top = False
    actions = None

    class Media:
        js = [
            "/static/admin/js/micromodal.min.js",
            "/static/admin/js/admin_modal.js",
        ]
        css = {
            "all": [
                "/static/admin/css/micromodal.css",
                "/static/admin/css/webhook_call.css",
            ]
        }

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # работает в форме редактирования, подтягивает inline-api_call
        queryset = queryset.select_related()
        return queryset

    @short_description("connection")
    def connection(self, obj):
        return str(obj.webhook.connection.name)

    @short_description("hook mode")
    def mode_(self, obj):
        return obj.webhook.get_mode_display()

    @boolean
    @short_description("ok?")
    def success_(self, obj):
        return obj.success

    @allow_tags
    def api_statuses(self, obj):
        res = ""
        for call in obj.api_calls.all().order_by("timestamp"):
            code = color_code(call.response_status, call.name)
            res += f"{code} • "
        return res.strip().strip("•")

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(APICall, site=admin_site)
class APICallAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "webhook",
        "method",
        "url",
        "status",
        "time",
        "response_body_trunc",
    )
    fieldsets = (
        (
            None,
            {
                "fields": ("connection", "webhook", "webhook_call"),
            },
        ),
        (
            "Request",
            {
                "fields": (
                    "timestamp",
                    "method",
                    "url",
                    "request_headers",
                    "request_body",
                ),
            },
        ),
        (
            "Response",
            {
                "fields": (
                    "response_status",
                    "duration",
                    "response_headers",
                    "response_body",
                ),
            },
        ),
        # ("connection", "webhook", "webhook_call"),
        # ("timestamp", "method", "url"),
        # "duration",
    )
    readonly_fields = [
        "connection",
        "webhook",
        "webhook_call",
        "timestamp",
        "method",
        "url",
        "request_headers",
        "request_body",
        "response_status",
        "duration",
        "response_headers",
        "response_body",
    ]
    ordering = ["-timestamp"]
    list_per_page = 30
    list_max_show_all = 1000
    actions_on_top = False
    actions = None

    def time(self, obj):
        if obj.duration is not None:
            return "{0:0.3f}".format(round(obj.duration, 3))

    @short_description("response body")
    def response_body_trunc(self, obj):
        return str(obj.response_body)[:100]

    @allow_tags
    def status(self, obj):
        return color_code(obj.response_status)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False
