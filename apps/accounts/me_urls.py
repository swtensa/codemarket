from django.urls import path
from django.views.generic import RedirectView

from apps.core.views import soon
from apps.purchases import views as purchase_views

from . import views

app_name = "me"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="me:purchases"), name="index"),
    path("purchases/", purchase_views.purchase_list, name="purchases"),
    path("purchases/<int:pk>/", purchase_views.purchase_detail, name="purchase"),
    path("purchases/<int:pk>/download/", purchase_views.download, name="download"),
    path("orders/", soon, name="orders"),
    path("profile/", views.profile, name="profile"),
]
