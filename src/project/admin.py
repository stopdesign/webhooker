from django.contrib.admin import AdminSite


class CustomAdminSite(AdminSite):
    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        # extra_context.update({"site_header": "dddd"})

        return super(CustomAdminSite, self).index(request, extra_context)


admin_site = CustomAdminSite(name="admin")
# admin_site.enable_nav_sidebar = False

from django.contrib.auth import get_user_model

User = get_user_model()

admin_site.register(User)
