"""Explicit product-level platform capabilities, separate from tenant RBAC scopes."""

from django.contrib.auth.models import Permission

from .models import User

PROVISION_TENANT = "organization.provision_tenant"
VIEW_TENANT_PROVISIONING = "organization.view_tenant_provisioning"
VIEW_PLATFORM_TENANT_DIRECTORY = "organization.view_platform_tenant_directory"

PLATFORM_CAPABILITIES = frozenset(
    {
        PROVISION_TENANT,
        VIEW_TENANT_PROVISIONING,
        VIEW_PLATFORM_TENANT_DIRECTORY,
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

    app_label, codenames = (
        "organization",
        {capability.split(".", maxsplit=1)[1] for capability in PLATFORM_CAPABILITIES},
    )
    direct = user.user_permissions.filter(
        content_type__app_label=app_label,
        codename__in=codenames,
    ).values_list("codename", flat=True)
    group = Permission.objects.filter(
        group__user=user,
        content_type__app_label=app_label,
        codename__in=codenames,
    ).values_list("codename", flat=True)
    return {f"{app_label}.{codename}" for codename in {*direct, *group}}


def has_platform_capability(user: User | None, capability: str) -> bool:
    """Check one declared platform capability against current database state."""

    if capability not in PLATFORM_CAPABILITIES:
        return False
    return capability in get_platform_capabilities(user)
