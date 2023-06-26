from django.urls import path, re_path

from main import views

app_name = "main"

urlpatterns = [
    # path("", views.dashboard, name="dashboard"),
    re_path(r"^hook/(?P<uid>[\w]{16})/?$", views.webhook_call, name="webhook_call"),
]
