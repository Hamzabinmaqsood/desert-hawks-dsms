"""Explicit product-level platform capabilities, separate from tenant RBAC scopes."""

from django.contrib.auth.models import Permission

from .models import User

PROVISION_TENANT = "organization.provision_tenant"
VIEW_TENANT_PROVISIONING = "organization.view_tenant_provisioning"
VIEW_PLATFORM_TENANT_DIRECTORY = "organization.view_platform_tenant_directory"
VIEW_PLAN_CATALOG = "subscriptions.view_plan_catalog"
MANAGE_PLAN_CATALOG = "subscriptions.manage_plan_catalog"
VIEW_COMMERCIAL_SUBSCRIPTIONS = "subscriptions.view_commercial_subscriptions"
MANAGE_COMMERCIAL_SUBSCRIPTIONS = "subscriptions.manage_commercial_subscriptions"

PLATFORM_CAPABILITIES = frozenset(
    {
        PROVISION_TENANT,
        VIEW_TENANT_PROVISIONING,
        VIEW_PLATFORM_TENANT_DIRECTORY,
        VIEW_PLAN_CATALOG,
        MANAGE_PLAN_CATALOG,
        VIEW_COMMERCIAL_SUBSCRIPTIONS,
        MANAGE_COMMERCIAL_SUBSCRIPTIONS,
    }
)


def get_platform_capabilities(user: User | None) -> set[str]:
    """Return current platform capabilities without consulting tenant assignments.

    Direct and Django-group permissions are deliberately used instead of a
    ``UserRoleAssignment``. A GLOBAL tenant assignment grants broad Company
    reach in the DSMS access engine and is therefore not a safe representation
    of platform-only authority.
    """

    if not user or not user.is_authenticated or not user.is_active:
        return set()
    if user.is_superuser:
        return set(PLATFORM_CAPABILITIES)

    direct = user.user_permissions.values_list("content_type__app_label", "codename")
    group = Permission.objects.filter(group__user=user).values_list(
        "content_type__app_label", "codename"
    )
    granted = {f"{app_label}.{codename}" for app_label, codename in {*direct, *group}}
    return granted & PLATFORM_CAPABILITIES


def has_platform_capability(user: User | None, capability: str) -> bool:
    """Check one declared platform capability against current database state."""

    if capability not in PLATFORM_CAPABILITIES:
        return False
    return capability in get_platform_capabilities(user)
