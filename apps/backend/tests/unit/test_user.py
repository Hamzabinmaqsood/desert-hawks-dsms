import pytest

from dsms.identity.models import User


@pytest.mark.django_db
def test_create_user_uses_email_and_hashes_password() -> None:
    user = User.objects.create_user(
        email="guard@EXAMPLE.COM",
        password="StrongTestPassword123!",
    )

    assert user.email == "guard@example.com"
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.check_password("StrongTestPassword123!")
    assert user.password != "StrongTestPassword123!"


@pytest.mark.django_db
def test_create_user_rejects_missing_email() -> None:
    with pytest.raises(ValueError, match="email address must be set"):
        User.objects.create_user(
            email="",
            password="StrongTestPassword123!",
        )


@pytest.mark.django_db
def test_create_user_without_password_has_unusable_password() -> None:
    user = User.objects.create_user(email="no-password@example.com")

    assert user.has_usable_password() is False


@pytest.mark.django_db
def test_create_superuser_sets_required_flags() -> None:
    user = User.objects.create_superuser(
        email="admin@example.com",
        password="StrongAdminPassword123!",
    )

    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.is_active is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"is_staff": False},
        {"is_superuser": False},
    ],
)
def test_create_superuser_rejects_invalid_flags(
    invalid_fields: dict[str, bool],
) -> None:
    with pytest.raises(ValueError, match="Superuser must have"):
        User.objects.create_superuser(
            email="invalid-admin@example.com",
            password="StrongAdminPassword123!",
            **invalid_fields,
        )


@pytest.mark.django_db
def test_user_string_representation_is_email() -> None:
    user = User.objects.create_user(
        email="display@example.com",
        password="StrongTestPassword123!",
    )

    assert str(user) == "display@example.com"
