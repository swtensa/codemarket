from django.urls import path

from apps.core.views import soon

from . import views

app_name = "moderation"

urlpatterns = [
    path("", views.queue, name="queue"),
    path("versions/<int:pk>/", views.version_detail, name="version"),
    path("users/", views.users, name="users"),
    path("users/<int:pk>/", views.user_action, name="user_action"),
    path("disputes/", soon, name="disputes"),
    path("payouts/", soon, name="payouts"),
    path("reports/", soon, name="reports"),
]
