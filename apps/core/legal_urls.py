from django.urls import path
from django.views.generic import TemplateView

app_name = "legal"

urlpatterns = [
    path("terms/", TemplateView.as_view(template_name="legal/terms.html"), name="terms"),
    path("seller/", TemplateView.as_view(template_name="legal/seller.html"), name="seller"),
    path("license/", TemplateView.as_view(template_name="legal/license.html"), name="license"),
    path("privacy/", TemplateView.as_view(template_name="legal/privacy.html"), name="privacy"),
]
