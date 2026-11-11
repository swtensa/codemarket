from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("buy/<slug:slug>/", views.buy, name="buy"),
]
