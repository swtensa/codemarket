from django.urls import path

from apps.balance import views as balance_views
from apps.disputes import views as dispute_views
from apps.reports import views as report_views

from . import views

app_name = "moderation"

urlpatterns = [
    path("", views.queue, name="queue"),
    path("versions/<int:pk>/", views.version_detail, name="version"),
    path("users/", views.users, name="users"),
    path("users/<int:pk>/", views.user_action, name="user_action"),
    path("disputes/", dispute_views.admin_list, name="disputes"),
    path("disputes/<int:pk>/", dispute_views.admin_detail, name="dispute"),
    path("payouts/", balance_views.payouts, name="payouts"),
    path("reports/", report_views.admin_reports, name="reports"),
    path("reports/excel/", report_views.admin_reports_excel, name="reports_excel"),
]
