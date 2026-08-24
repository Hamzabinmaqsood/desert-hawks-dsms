"""Transport-layer validation for the workforce module.

Read serializers shape model instances for responses; write serializers
validate and normalize incoming payloads. Views pass ``validated_data`` into
the corresponding service function rather than calling ``serializer.save()``
directly, so business rules stay in :mod:`dsms.workforce.services`.
``EmployeeDetailSerializer.national_identity_number`` only resolves to the
real value for callers holding ``workforce.view_sensitive_employee_data`` --
everyone else sees the masked form only.
"""

from typing import Any

from rest_framework import serializers
from rest_framework.request import Request

from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department, Designation
from dsms.workforce.enums import (
    AddressType,
    EmployeeType,
    EmploymentType,
    Gender,
    MaritalStatus,
)
from dsms.workforce.models import (
    EmergencyContact,
    Employee,
    EmployeeAddress,
    EmployeeAssignmentHistory,
    EmployeeStatusHistory,
)

# --------------------------------------------------------------------------
# Employee
# --------------------------------------------------------------------------


class EmployeeListSerializer(serializers.ModelSerializer[Employee]):
    full_name = serializers.CharField(read_only=True)
    company_name = serializers.CharField(source="company.legal_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    designation_name = serializers.CharField(
        source="designation.name", read_only=True, default=None
    )

    class Meta:
        model = Employee
        fields = [
            "id",
            "employee_number",
            "full_name",
            "employee_type",
            "employment_status",
            "company",
            "company_name",
            "branch",
            "branch_name",
            "department",
            "department_name",
            "designation",
            "designation_name",
            "mobile_number",
            "is_active",
        ]
        read_only_fields = fields


class EmployeeDetailSerializer(serializers.ModelSerializer[Employee]):
    full_name = serializers.CharField(read_only=True)
    company_name = serializers.CharField(source="company.legal_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    designation_name = serializers.CharField(
        source="designation.name", read_only=True, default=None
    )
    user_email = serializers.CharField(source="user.email", read_only=True, default=None)
    masked_national_identity_number = serializers.CharField(read_only=True)
    national_identity_number = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id",
            "employee_number",
            "user",
            "user_email",
            "company",
            "company_name",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "preferred_name",
            "father_or_spouse_name",
            "gender",
            "date_of_birth",
            "marital_status",
            "nationality",
            "national_identity_number",
            "masked_national_identity_number",
            "national_identity_expiry",
            "personal_email",
            "mobile_number",
            "alternate_mobile_number",
            "employee_type",
            "employment_type",
            "employment_status",
            "joining_date",
            "confirmation_date",
            "probation_end_date",
            "exit_date",
            "branch",
            "branch_name",
            "department",
            "department_name",
            "designation",
            "designation_name",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_national_identity_number(self, obj: Employee) -> str | None:
        request: Request | None = self.context.get("request")
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and (
                user.is_superuser
                or "workforce.view_sensitive_employee_data"
                in access.get_effective_permissions(user)
            )
        ):
            return obj.national_identity_number
        return None

    def get_notes(self, obj: Employee) -> str | None:
        """Treat internal notes as sensitive detail, like the full identity value."""
        request: Request | None = self.context.get("request")
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and (
                user.is_superuser
                or "workforce.view_sensitive_employee_data"
                in access.get_effective_permissions(user)
            )
        ):
            return obj.notes
        return None


class EmployeeWriteSerializer(serializers.Serializer[Any]):
    """Used for both create and partial-update.

    ``employee_number``, ``company``, ``branch``, ``department``, and
    ``designation`` are accepted on create but the view rejects them on
    update -- the employee number is immutable once assigned, and
    organizational reassignment must go through ``change-assignment`` so it
    is scope-checked and history-tracked.
    """

    employee_number = serializers.CharField(max_length=32)
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    first_name = serializers.CharField(max_length=150)
    middle_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    preferred_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    father_or_spouse_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=Gender.choices, required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    marital_status = serializers.ChoiceField(choices=MaritalStatus.choices, required=False)
    nationality = serializers.CharField(max_length=2, required=False)
    national_identity_number = serializers.CharField(
        max_length=32, required=False, allow_blank=True
    )
    national_identity_expiry = serializers.DateField(required=False, allow_null=True)
    personal_email = serializers.EmailField(required=False, allow_blank=True)
    mobile_number = serializers.CharField(max_length=20)
    alternate_mobile_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    employee_type = serializers.ChoiceField(choices=EmployeeType.choices)
    employment_type = serializers.ChoiceField(choices=EmploymentType.choices)
    joining_date = serializers.DateField()
    confirmation_date = serializers.DateField(required=False, allow_null=True)
    probation_end_date = serializers.DateField(required=False, allow_null=True)
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    designation = serializers.PrimaryKeyRelatedField(
        queryset=Designation.objects.all(), required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_employee_number(self, value: str) -> str:
        return value.strip().upper()


# --------------------------------------------------------------------------
# Employment lifecycle actions
# --------------------------------------------------------------------------


class StatusChangeSerializer(serializers.Serializer[Any]):
    effective_date = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True)


class TerminalStatusChangeSerializer(StatusChangeSerializer):
    exit_date = serializers.DateField()


class ChangeAssignmentSerializer(serializers.Serializer[Any]):
    effective_from = serializers.DateField()
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    designation = serializers.PrimaryKeyRelatedField(
        queryset=Designation.objects.all(), required=False, allow_null=True
    )
    reason = serializers.CharField(required=False, allow_blank=True)


class LinkUserSerializer(serializers.Serializer[Any]):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())


# --------------------------------------------------------------------------
# History (read-only)
# --------------------------------------------------------------------------


class EmployeeStatusHistorySerializer(serializers.ModelSerializer[EmployeeStatusHistory]):
    changed_by_email = serializers.CharField(
        source="changed_by.email", read_only=True, default=None
    )

    class Meta:
        model = EmployeeStatusHistory
        fields = [
            "id",
            "previous_status",
            "new_status",
            "effective_date",
            "reason",
            "changed_by",
            "changed_by_email",
            "created_at",
        ]
        read_only_fields = fields


class EmployeeAssignmentHistorySerializer(serializers.ModelSerializer[EmployeeAssignmentHistory]):
    company_name = serializers.CharField(source="company.legal_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    designation_name = serializers.CharField(
        source="designation.name", read_only=True, default=None
    )
    changed_by_email = serializers.CharField(
        source="changed_by.email", read_only=True, default=None
    )

    class Meta:
        model = EmployeeAssignmentHistory
        fields = [
            "id",
            "company",
            "company_name",
            "branch",
            "branch_name",
            "department",
            "department_name",
            "designation",
            "designation_name",
            "effective_from",
            "effective_to",
            "reason",
            "changed_by",
            "changed_by_email",
            "created_at",
        ]
        read_only_fields = fields


# --------------------------------------------------------------------------
# Addresses
# --------------------------------------------------------------------------


class EmployeeAddressReadSerializer(serializers.ModelSerializer[EmployeeAddress]):
    class Meta:
        model = EmployeeAddress
        fields = [
            "id",
            "employee",
            "address_type",
            "address_line_1",
            "address_line_2",
            "city",
            "province_or_state",
            "postal_code",
            "country_code",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class EmployeeAddressWriteSerializer(serializers.Serializer[Any]):
    address_type = serializers.ChoiceField(choices=AddressType.choices)
    address_line_1 = serializers.CharField(max_length=255)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    province_or_state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country_code = serializers.CharField(max_length=2, required=False)
    is_primary = serializers.BooleanField(required=False)


# --------------------------------------------------------------------------
# Emergency contacts
# --------------------------------------------------------------------------


class EmergencyContactReadSerializer(serializers.ModelSerializer[EmergencyContact]):
    class Meta:
        model = EmergencyContact
        fields = [
            "id",
            "employee",
            "name",
            "relationship",
            "mobile_number",
            "alternate_mobile_number",
            "address",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class EmergencyContactWriteSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150)
    relationship = serializers.CharField(max_length=100)
    mobile_number = serializers.CharField(max_length=20)
    alternate_mobile_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False)


__all__ = [
    "ChangeAssignmentSerializer",
    "EmergencyContactReadSerializer",
    "EmergencyContactWriteSerializer",
    "EmployeeAddressReadSerializer",
    "EmployeeAddressWriteSerializer",
    "EmployeeAssignmentHistorySerializer",
    "EmployeeDetailSerializer",
    "EmployeeListSerializer",
    "EmployeeStatusHistorySerializer",
    "EmployeeWriteSerializer",
    "LinkUserSerializer",
    "StatusChangeSerializer",
    "TerminalStatusChangeSerializer",
]
