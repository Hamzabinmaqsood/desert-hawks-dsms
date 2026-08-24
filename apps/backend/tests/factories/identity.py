from typing import Any

import factory
from factory.django import DjangoModelFactory

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User, UserRoleAssignment


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"
    is_staff = False
    is_active = True

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> User:
        password = kwargs.pop("password", "StrongTestPassword123!")
        manager = cls._get_manager(model_class)  # type: ignore[attr-defined]
        return manager.create_user(*args, password=password, **kwargs)  # type: ignore[no-any-return]


class RoleFactory(DjangoModelFactory[Role]):
    class Meta:
        model = Role

    company = None
    code = factory.Sequence(lambda n: f"ROLE{n:04d}")
    name = factory.Sequence(lambda n: f"Role {n}")
    is_system = False
    is_active = True


class UserRoleAssignmentFactory(DjangoModelFactory[UserRoleAssignment]):
    class Meta:
        model = UserRoleAssignment

    user: User = factory.SubFactory(UserFactory)  # type: ignore[assignment]
    role: Role = factory.SubFactory(RoleFactory)  # type: ignore[assignment]
    scope_type = AccessScopeType.GLOBAL
    is_active = True
