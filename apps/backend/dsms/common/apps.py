from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dsms.common"

    def ready(self) -> None:
        # Django Admin is an internal, staff-only console for this deployment,
        # so it carries the Desert Hawks identity rather than the stock Django
        # labels. Applied at app load rather than in the URLconf so the
        # branding does not depend on URL resolution having happened first.
        from django.contrib import admin

        admin.site.site_header = "Desert Hawks Administration"
        admin.site.site_title = "Desert Hawks Admin"
        admin.site.index_title = "Digital Transformation System"
