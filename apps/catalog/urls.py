from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.index, name="index"),
    path("p/<slug:slug>/", views.product_detail, name="product"),
]
