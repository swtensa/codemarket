from datetime import datetime

from pydantic import BaseModel

from .common import Schema


class UserOut(Schema):
    id: int
    email: str
    username: str
    github_login: str
    is_staff: bool
    is_seller: bool
    status: str
    created_at: datetime
    terms_accepted_at: datetime | None
    seller_terms_accepted_at: datetime | None


class UserShort(Schema):
    id: int
    username: str


class RegisterIn(BaseModel):
    email: str = ""
    username: str = ""
    password1: str = ""
    password2: str = ""
    accept_terms: bool = False


class LoginIn(BaseModel):
    email: str = ""
    password: str = ""


class PasswordChangeIn(BaseModel):
    old_password: str = ""
    new_password1: str = ""
    new_password2: str = ""


class ResetRequestIn(BaseModel):
    email: str = ""


class ResetConfirmIn(BaseModel):
    token: str
    new_password1: str = ""
    new_password2: str = ""


class ProfileIn(BaseModel):
    username: str = ""
    github_login: str = ""


class GithubLoginIn(BaseModel):
    github_login: str = ""


class SiteConfig(BaseModel):
    hold_days: int
    license_version: str
    max_revisions: int
    auto_accept_days: int
    payment_provider: str
    github_mode: str
    commission_percent: int
    min_payout: int
    payment_timeout_min: int


class AdminUserOut(Schema):
    id: int
    email: str
    username: str
    github_login: str
    is_staff: bool
    is_seller: bool
    status: str
    block_reason: str
    created_at: datetime
    last_login: datetime | None
