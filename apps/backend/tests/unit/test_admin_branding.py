from django.contrib import admin


def test_django_admin_carries_desert_hawks_identity() -> None:
    """The staff console is branded for Desert Hawks, not stock Django."""
    assert admin.site.site_header == "Desert Hawks Administration"
    assert admin.site.site_title == "Desert Hawks Admin"
    assert admin.site.index_title == "Digital Transformation System"
