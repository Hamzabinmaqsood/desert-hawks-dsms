import pytest
from django.contrib.auth.models import Group, Permission

from dsms.identity.platform_access import (
    PLATFORM_CAPABILITIES,
    PROVISION_TENANT,
    VIEW_PLATFORM_TENANT_DIRECTORY,
    get_platform_capabilities,
    has_platform_capability,
)
from tests.factories.identity import UserFactory

pytestmark = pytest.mark.django_db


def permission(capability: str) -> Permission:
    app_label, codename = capability.split(".", maxsplit=1)
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def test_direct_platform_capability_is_independent_of_staff_and_tenant_rbac() -> None:
    operator = UserFactory.create(is_staff=False, is_superuser=False)
    operator.user_permissions.add(permission(PROVISION_TENANT))

    assert has_platform_capability(operator, PROVISION_TENANT)
    assert get_platform_capabilities(operator) == {PROVISION_TENANT}
    assert operator.role_assignments.count() == 0


def test_group_capability_is_supported_without_global_tenant_assignment() -> None:
    operator = UserFactory.create()
    group = Group.objects.create(name="Trusted platform provisioning operators")
    group.permissions.add(permission(VIEW_PLATFORM_TENANT_DIRECTORY))
    operator.groups.add(group)

    assert has_platform_capability(operator, VIEW_PLATFORM_TENANT_DIRECTORY)
    assert operator.role_assignments.count() == 0


def test_staff_only_inactive_and_revoked_users_fail_closed() -> None:
    staff = UserFactory.create(is_staff=True)
    assert get_platform_capabilities(staff) == set()

    operator = UserFactory.create()
    grant = permission(PROVISION_TENANT)
    operator.user_permissions.add(grant)
    assert has_platform_capability(operator, PROVISION_TENANT)
    operator.user_permissions.remove(grant)
    assert not has_platform_capability(operator, PROVISION_TENANT)

    operator.user_permissions.add(grant)
    operator.is_active = False
    operator.save(update_fields=["is_active"])
    assert get_platform_capabilities(operator) == set()


def test_active_superuser_is_explicit_break_glass_platform_authority() -> None:
    superuser = UserFactory.create(is_staff=True, is_superuser=True)
    assert get_platform_capabilities(superuser) == set(PLATFORM_CAPABILITIES)

    superuser.is_active = False
    superuser.save(update_fields=["is_active"])
    assert get_platform_capabilities(superuser) == set()
