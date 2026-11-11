from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-created_at"]
    list_display = ["email", "username", "status", "is_staff", "github_login", "created_at"]
    list_filter = ["status", "is_staff"]
    search_fields = ["email", "username", "github_login"]
    readonly_fields = ["created_at", "last_login", "terms_accepted_at", "seller_terms_accepted_at"]
    fieldsets = [
        (None, {"fields": ["email", "username", "password"]}),
        ("GitHub", {"fields": ["github_login", "github_installation_id"]}),
        ("Статус", {"fields": ["status", "block_reason", "is_active", "is_staff", "is_superuser"]}),
        ("Даты", {"fields": ["created_at", "last_login", "terms_accepted_at", "seller_terms_accepted_at"]}),
    ]
    add_fieldsets = [(None, {"classes": ["wide"], "fields": ["email", "username", "password1", "password2"]})]
