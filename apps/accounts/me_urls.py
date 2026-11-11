from django.urls import path
from django.views.generic import RedirectView

from apps.core.views import soon

from . import views

app_name = "me"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="me:purchases"), name="index"),
    path("purchases/", soon, name="purchases"),
    path("orders/", soon, name="orders"),
    path("profile/", views.profile, name="profile"),
]
