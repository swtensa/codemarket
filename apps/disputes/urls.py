from django.urls import path

from . import views

app_name = "disputes"

urlpatterns = [
    path("new/", views.new_dispute, name="new"),
]
