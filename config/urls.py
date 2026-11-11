from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "CodeMarket — администрирование"
admin.site.site_title = "CodeMarket"


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("me/", include("apps.accounts.me_urls")),
    path("legal/", include("apps.core.legal_urls")),
    path("sell/", include("apps.catalog.sell_urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("balance/", include("apps.balance.urls")),
    path("disputes/", include("apps.disputes.urls")),
    path("moderation/", include("apps.moderation.urls")),
    path("payments/", include("apps.payments.urls")),
    path("orders/", include("apps.orders.urls")),
    path("github/", include("apps.integrations.github.urls")),
    path("", include("apps.purchases.urls")),
    path("", include("apps.catalog.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
