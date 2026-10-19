from django.conf import settings
from django.contrib import admin


def test_django_admin_uses_neutral_platform_identity() -> None:
    assert admin.site.site_header == "Business Operations Platform Administration"
    assert admin.site.site_title == "Business Operations Platform Admin"
    assert admin.site.index_title == "Business Operations Platform"


def test_openapi_uses_neutral_platform_identity() -> None:
    assert settings.SPECTACULAR_SETTINGS["TITLE"] == ("Business Operations Platform API")
