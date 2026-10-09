from django.contrib import admin


def test_django_admin_uses_neutral_platform_identity() -> None:
    assert admin.site.site_header == "DSMS Administration"
    assert admin.site.site_title == "DSMS Admin"
    assert admin.site.index_title == "Security Management Platform"
