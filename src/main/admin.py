import json

from django.contrib import admin
from django.forms import TextInput, widgets
from django.db.models import Count
from django.utils.safestring import mark_safe
from project.admin import admin_site
from project.helpers.admin_decorators import allow_tags, short_description, boolean
from .models import APICall, Connection, WebhookCall, Webhook


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
    list_display = ("uid", "connection", "call_count", "created_at")
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


class PopupWidget(TextInput):
    class Media:
        css = {
            'all': ('path/to/custom.css',)
        }
        js = ('path/to/custom.js',)

    def render(self, name, value, attrs=None, renderer=None):

        if value:
            truncated_value = value[:200]
            full_value = value.replace("'", r"\'")
            popup_script = f"openPopup('{full_value}');"
            attrs["onclick"] = popup_script
            return mark_safe(f"{modal_tmpl}  {truncated_value}<br/><small data-micromodal-trigger='modal-1'>(Click to view full text)</small>")
        else:
            return ""

    def _format_value(self, value):
        return value


modal_tmpl = """
  <div class="modal micromodal-slide" id="modal-1" aria-hidden="true">
    <div class="modal__overlay" tabindex="-1" data-micromodal-close>
      <div class="modal__container" role="dialog" aria-modal="true" aria-labelledby="modal-1-title">
        <header class="modal__header">
          <div class="modal__title" id="modal-1-title">
            Response body
          </div>
          <button class="modal__close" aria-label="Close modal" data-micromodal-close></button>
        </header>
        <main class="modal__content" id="modal-1-content">
          <p>
            Try hitting the <code>tab</code> key and notice how the focus stays within the modal itself. Also, <code>esc</code> to close modal.
          </p>
        </main>
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
        # return str(obj.response_body)[:100]
        if value:
            truncated_value = value[:150]
            # popup_script = f"openPopup('{full_value}');"
            # attrs["onclick"] = popup_script
            return mark_safe(f"<span class='micromodal-trigger' data-micromodal-trigger='modal-1'>{truncated_value}</span>{modal_tmpl}")
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
        "request_body",
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
    exclude = (
        'request_headers',
    )
    ordering = ["-timestamp"]
    inlines = [APICallInline]
    list_per_page = 30
    list_max_show_all = 1000
    actions_on_top = False
    actions = None

    class Media:
        js = [
            "https://unpkg.com/micromodal/dist/micromodal.min.js",
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
        queryset = queryset.prefetch_related("api_calls")
        return queryset

    @short_description("connection")
    def connection(self, obj):
        return str(obj.webhook.connection.name)

    @short_description("hook mode")
    def mode_(self, obj):
        return str(obj.webhook.mode).title()

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
        (None, {
           'fields': ("connection", "webhook", "webhook_call"),
        }),
        ('Request', {
            'fields': ("timestamp", "method", "url", "request_headers", "request_body"),
        }),
        ('Response', {
            'fields': ("response_status", "duration", "response_headers", "response_body"),
        }),
        # ("connection", "webhook", "webhook_call"),
        # ("timestamp", "method", "url"),
        # "duration",
    )
    readonly_fields = [
        "connection", "webhook", "webhook_call",
        "timestamp", "method", "url", "request_headers", "request_body",
        "response_status", "duration", "response_headers", "response_body",
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
