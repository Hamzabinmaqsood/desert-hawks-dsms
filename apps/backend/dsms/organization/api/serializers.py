"""Transport-layer validation for the organization module.

Read serializers shape model instances (including related display values)
for responses. Write serializers validate and normalize incoming payloads;
views pass their ``validated_data`` into the corresponding service function
rather than calling ``serializer.save()`` directly, so business rules stay
in :mod:`dsms.organization.services`.
"""

from typing import Any

from rest_framework import serializers

from dsms.identity import access as identity_access
from dsms.identity.models import User
from dsms.organization.business_defaults import (
    normalize_currency_code,
    validate_currency_code,
    validate_timezone_name,
)
from dsms.organization.enums import DepartmentScope
from dsms.organization.models import (
    Branch,
    City,
    Company,
    Department,
    Designation,
    OperationalZone,
    Region,
)


class _TenantScopedOrganizationWriteMixin:
    """Constrain organizational references and forbid ownership transfer."""

    instance: Any

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = getattr(self, "context", {}).get("request")
        user = getattr(request, "user", None)
        if not isinstance(user, User) or user.is_superuser:
            return
        queryset_ids = {
            "company": identity_access.get_accessible_company_ids(user),
            "region": identity_access.get_accessible_region_ids(user),
            "branch": identity_access.get_accessible_branch_ids(user),
            "department": identity_access.get_accessible_department_ids(user),
            "operational_zone": identity_access.get_accessible_operational_zone_ids(user),
        }
        for name, ids in queryset_ids.items():
            field = getattr(self, "fields", {}).get(name)
            if isinstance(field, serializers.PrimaryKeyRelatedField) and field.queryset is not None:
                field.queryset = field.queryset.filter(pk__in=ids)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        company = attrs.get("company") or getattr(instance, "company", None)
        if (
            instance is not None
            and "company" in attrs
            and attrs["company"].pk != instance.company_id
        ):
            raise serializers.ValidationError(
                {"company": "Company ownership cannot be changed after creation."}
            )
        errors: dict[str, str] = {}
        for name in ("region", "branch", "department", "operational_zone", "parent"):
            related = attrs.get(name)
            if related is not None and getattr(related, "company_id", None) != getattr(
                company, "pk", None
            ):
                errors[name] = "Must belong to the selected company."
        city = attrs.get("city", getattr(instance, "city", None))
        region = attrs.get("region") or getattr(instance, "region", None)
        if city is not None and (
            city.company_id != getattr(company, "pk", None)
            or city.region_id != getattr(region, "pk", None)
        ):
            errors["city"] = "Must belong to the selected company and region."
        branch = attrs.get("branch", getattr(instance, "branch", None))
        if branch is not None and region is not None and branch.region_id != region.pk:
            errors["branch"] = "Must belong to the selected region."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class _NormalizedCodeMixin:
    def validate_code(self, value: str) -> str:
        return value.strip().upper()


class _NormalizedCountryCodeMixin:
    def validate_country_code(self, value: str) -> str:
        return value.strip().upper()


# --------------------------------------------------------------------------
# Company
# --------------------------------------------------------------------------


class CompanyReadSerializer(serializers.ModelSerializer[Company]):
    class Meta:
        model = Company
        fields = [
            "id",
            "code",
            "legal_name",
            "trade_name",
            "registration_number",
            "tax_number",
            "email",
            "phone",
            "website",
            "timezone",
            "default_currency",
            "invoice_number_prefix",
            "receipt_number_prefix",
            "credit_note_number_prefix",
            "debit_note_number_prefix",
            "address_line_1",
            "address_line_2",
            "city_name",
            "province_name",
            "postal_code",
            "country_code",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CompanyWriteSerializer(
    _NormalizedCodeMixin, _NormalizedCountryCodeMixin, serializers.Serializer[Any]
):
    code = serializers.CharField(max_length=20)
    legal_name = serializers.CharField(max_length=255)
    trade_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    registration_number = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    tax_number = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=64, required=False)
    default_currency = serializers.CharField(max_length=3, required=False)
    address_line_1 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    province_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country_code = serializers.CharField(max_length=2, required=False)

    def validate_default_currency(self, value: str) -> str:
        normalized = normalize_currency_code(value)
        validate_currency_code(normalized)
        return normalized

    def validate_timezone(self, value: str) -> str:
        normalized = value.strip()
        validate_timezone_name(normalized)
        return normalized

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is None:
            missing = {
                name: ["This field is required when creating a Company."]
                for name in ("timezone", "default_currency", "country_code")
                if name not in attrs
            }
            if missing:
                raise serializers.ValidationError(missing)
        return attrs


# --------------------------------------------------------------------------
# Region
# --------------------------------------------------------------------------


class RegionReadSerializer(serializers.ModelSerializer[Region]):
    company_name = serializers.CharField(source="company.legal_name", read_only=True)

    class Meta:
        model = Region
        fields = [
            "id",
            "company",
            "company_name",
            "code",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RegionWriteSerializer(
    _TenantScopedOrganizationWriteMixin, _NormalizedCodeMixin, serializers.Serializer[Any]
):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True)


# --------------------------------------------------------------------------
# City
# --------------------------------------------------------------------------


class CityReadSerializer(serializers.ModelSerializer[City]):
    company_name = serializers.CharField(source="company.legal_name", read_only=True)
    region_name = serializers.CharField(source="region.name", read_only=True)

    class Meta:
        model = City
        fields = [
            "id",
            "company",
            "company_name",
            "region",
            "region_name",
            "code",
            "name",
            "province_or_state",
            "country_code",
            "timezone",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CityWriteSerializer(
    _TenantScopedOrganizationWriteMixin,
    _NormalizedCodeMixin,
    _NormalizedCountryCodeMixin,
    serializers.Serializer[Any],
):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all())
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=150)
    province_or_state = serializers.CharField(max_length=150)
    country_code = serializers.CharField(max_length=2, required=False)
    timezone = serializers.CharField(max_length=64, required=False)

    def validate_timezone(self, value: str) -> str:
        normalized = value.strip()
        validate_timezone_name(normalized)
        return normalized


# --------------------------------------------------------------------------
# Branch
# --------------------------------------------------------------------------


class BranchReadSerializer(serializers.ModelSerializer[Branch]):
    company_name = serializers.CharField(source="company.legal_name", read_only=True)
    region_name = serializers.CharField(source="region.name", read_only=True)
    city_name = serializers.CharField(source="city.name", read_only=True)

    class Meta:
        model = Branch
        fields = [
            "id",
            "company",
            "company_name",
            "region",
            "region_name",
            "city",
            "city_name",
            "code",
            "name",
            "email",
            "phone",
            "address_line_1",
            "address_line_2",
            "postal_code",
            "latitude",
            "longitude",
            "is_head_office",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class BranchWriteSerializer(
    _TenantScopedOrganizationWriteMixin, _NormalizedCodeMixin, serializers.Serializer[Any]
):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all())
    city = serializers.PrimaryKeyRelatedField(queryset=City.objects.all())
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    address_line_1 = serializers.CharField(max_length=255)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    is_head_office = serializers.BooleanField(required=False)


# --------------------------------------------------------------------------
# Department
# --------------------------------------------------------------------------


class DepartmentReadSerializer(serializers.ModelSerializer[Department]):
    company_name = serializers.CharField(source="company.legal_name", read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = Department
        fields = [
            "id",
            "company",
            "company_name",
            "parent",
            "parent_name",
            "branch",
            "branch_name",
            "code",
            "name",
            "scope",
            "description",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DepartmentWriteSerializer(
    _TenantScopedOrganizationWriteMixin, _NormalizedCodeMixin, serializers.Serializer[Any]
):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    parent = serializers.PrimaryKeyRelatedField(  # type: ignore[assignment]
        # "parent" is a valid DRF field name (DRF collects declared fields via
        # its metaclass); it only collides with Field.parent's *type* stub.
        queryset=Department.objects.all(),
        required=False,
        allow_null=True,
    )
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True
    )
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=150)
    scope = serializers.ChoiceField(choices=DepartmentScope.choices)
    description = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False, min_value=0)


# --------------------------------------------------------------------------
# Designation
# --------------------------------------------------------------------------


class DesignationReadSerializer(serializers.ModelSerializer[Designation]):
    company_name = serializers.CharField(source="company.legal_name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = Designation
        fields = [
            "id",
            "company",
            "company_name",
            "department",
            "department_name",
            "code",
            "name",
            "level",
            "sort_order",
            "is_supervisory",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DesignationWriteSerializer(
    _TenantScopedOrganizationWriteMixin, _NormalizedCodeMixin, serializers.Serializer[Any]
):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=150)
    level = serializers.IntegerField(min_value=1)
    sort_order = serializers.IntegerField(required=False, min_value=0)
    is_supervisory = serializers.BooleanField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)


# --------------------------------------------------------------------------
# Operational Zone
# --------------------------------------------------------------------------


class OperationalZoneReadSerializer(serializers.ModelSerializer[OperationalZone]):
    company_name = serializers.CharField(source="company.legal_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = OperationalZone
        fields = [
            "id",
            "company",
            "company_name",
            "branch",
            "branch_name",
            "code",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OperationalZoneWriteSerializer(
    _TenantScopedOrganizationWriteMixin, _NormalizedCodeMixin, serializers.Serializer[Any]
):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True)


# --------------------------------------------------------------------------
# Hierarchy (read-only, nested)
# --------------------------------------------------------------------------


class HierarchyCitySerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class HierarchyOperationalZoneSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class HierarchyBranchSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_head_office = serializers.BooleanField()
    is_active = serializers.BooleanField()
    operational_zones = HierarchyOperationalZoneSerializer(many=True)


class HierarchyRegionSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()
    cities = HierarchyCitySerializer(many=True)
    branches = HierarchyBranchSerializer(many=True)


class HierarchyDepartmentSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    scope = serializers.CharField()
    sort_order = serializers.IntegerField()
    is_active = serializers.BooleanField()
    branch_id = serializers.UUIDField(allow_null=True)
    branch_name = serializers.CharField(allow_null=True)
    children = serializers.SerializerMethodField()

    def get_children(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        serializer = HierarchyDepartmentSerializer(obj["children"], many=True)
        return list(serializer.data)


class HierarchyDesignationSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    level = serializers.IntegerField()
    is_supervisory = serializers.BooleanField()
    is_active = serializers.BooleanField()
    department_id = serializers.UUIDField(allow_null=True)
    department_name = serializers.CharField(allow_null=True)


class OrganizationHierarchySerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    legal_name = serializers.CharField()
    is_active = serializers.BooleanField()
    regions = HierarchyRegionSerializer(many=True)
    departments = HierarchyDepartmentSerializer(many=True)
    designations = HierarchyDesignationSerializer(many=True)
