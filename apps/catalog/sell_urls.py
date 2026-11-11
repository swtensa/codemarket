from django.urls import path

from apps.integrations.github import views as github_views
from apps.orders import views as order_views
from apps.reports import views as report_views
from apps.versions import views as version_views

from . import sell_views

app_name = "sell"

urlpatterns = [
    path("", sell_views.dashboard, name="dashboard"),
    path("github/", github_views.connect, name="github"),
    path("orders/", order_views.seller_list, name="orders"),
    path("stats/", report_views.seller_stats, name="stats"),
    path("github/callback/", github_views.callback, name="github_callback"),
    path("products/new/", sell_views.product_new, name="product_new"),
    path("products/<int:pk>/edit/", sell_views.product_edit, name="product_edit"),
    path("products/<int:pk>/media/", sell_views.product_media, name="product_media"),
    path("products/<int:pk>/screenshots/<int:sid>/delete/", sell_views.screenshot_delete, name="screenshot_delete"),
    path("products/<int:pk>/versions/", version_views.versions, name="versions"),
    path("products/<int:pk>/versions/import/", version_views.import_release, name="import_release"),
    path("versions/<int:vid>/appeal/", version_views.appeal, name="appeal"),
    path("products/<int:pk>/<slug:action>/", sell_views.product_action, name="product_action"),
]
