from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dsms.common"

    def ready(self) -> None:
        # Django Admin is a global platform surface, not selected-Company UX.
        # Keep its identity neutral and independent from tenant session state.
        from django.contrib import admin

        admin.site.site_header = "DSMS Administration"
        admin.site.site_title = "DSMS Admin"
        admin.site.index_title = "Security Management Platform"
