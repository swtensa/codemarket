from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("webhook/", views.webhook, name="webhook"),
    path("return/<int:pk>/", views.payment_return, name="return"),
    path("fake/<str:external_id>/", views.fake_checkout, name="fake"),
]
