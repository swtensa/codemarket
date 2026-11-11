from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.views import soon

admin.site.site_header = "CodeMarket — администрирование"
admin.site.site_title = "CodeMarket"


def _stub(namespace, *names):
    """Заглушки разделов, которые появятся на следующих этапах."""
    return include(([path(f"{namespace}/{n}/", soon, name=n) for n in names], namespace))


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("me/", include("apps.accounts.me_urls")),
    path("legal/", include("apps.core.legal_urls")),
    path("sell/", include("apps.catalog.sell_urls")),
    path("_/", _stub("notifications", "list")),
    path("balance/", include("apps.balance.urls")),
    path("disputes/", include("apps.disputes.urls")),
    path("moderation/", include("apps.moderation.urls")),
    path("payments/", include("apps.payments.urls")),
    path("orders/", include("apps.orders.urls")),
    path("", include("apps.purchases.urls")),
    path("", include("apps.catalog.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
