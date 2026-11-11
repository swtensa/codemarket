from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("new/", views.new_order, name="new"),
    path("<int:pk>/", views.order_detail, name="detail"),
    path("<int:pk>/messages/", views.poll_messages, name="messages"),
    path("attachments/<int:message_id>/", views.attachment, name="attachment"),
]
