from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.views import soon

admin.site.site_header = "CodeMarket — администрирование"
admin.site.site_title = "CodeMarket"

stub = [
    path("me/purchases/", soon, name="purchases"),
    path("me/orders/", soon, name="orders"),
    path("me/profile/", soon, name="profile"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("legal/", include("apps.core.legal_urls")),
    path("accounts/login/", soon, name="login"),
    path("", include((stub, "me"))),
    path(
        "",
        include(
            (
                [
                    path("accounts/login/", soon, name="login"),
                    path("accounts/logout/", soon, name="logout"),
                    path("accounts/register/", soon, name="register"),
                ],
                "accounts",
            )
        ),
    ),
    path("", include(([path("sell/", soon, name="dashboard")], "sell"))),
    path("", include(([path("notifications/", soon, name="list")], "notifications"))),
    path("", include(([path("balance/", soon, name="index")], "balance"))),
    path("", include(([path("moderation/", soon, name="queue")], "moderation"))),
    path("", include("apps.catalog.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
