from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import Q
from django.utils import timezone

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.documents.models import DocumentType
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, OperationalZone
from dsms.training.models import QualificationType
from dsms.workforce.enums import EmployeeType
from dsms.workforce.models import Employee

from .enums import (
    ClientStatus,
    ContactType,
    ContractChangeType,
    ContractStatus,
    ContractType,
    CoverageType,
    PostStatus,
    RequirementLevel,
    ServiceType,
    SiteRiskLevel,
    SiteStatus,
    SLAType,
    StaffingRequirementStatus,
    Weekday,
)


class ContractModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class ClientIndustry(ContractModel, ActiveModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_client_industry_code")
        ]


class Client(ContractModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="clients")
    client_code = models.CharField(max_length=50)
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True)
    industry = models.ForeignKey(ClientIndustry, on_delete=models.PROTECT)
    registration_number = models.CharField(max_length=100, blank=True)
    tax_number = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    main_email = models.EmailField(blank=True)
    main_phone = models.CharField(max_length=30, blank=True)
    billing_address = models.TextField(blank=True)
    head_office_address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    province_or_state = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=2, default="PK")
    status = models.CharField(
        max_length=20, choices=ClientStatus.choices, default=ClientStatus.PROSPECT
    )
    notes = models.TextField(blank=True)
    account_manager = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "client_code"], name="uniq_client_code_company"
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.client_code = self.client_code.strip().upper()
        self.legal_name = self.legal_name.strip()
        super().save(*args, **kwargs)


class ClientContact(ContractModel, ActiveModel):
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="contacts")
    name = models.CharField(max_length=200)
    designation = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    mobile_number = models.CharField(max_length=30, blank=True)
    office_phone = models.CharField(max_length=30, blank=True)
    contact_type = models.CharField(max_length=20, choices=ContactType.choices)
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client"],
                condition=Q(is_primary=True, is_active=True),
                name="uniq_active_primary_client_contact",
            )
        ]


class ServiceContract(ContractModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="service_contracts")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="contracts")
    contract_number = models.CharField(max_length=50)
    contract_type = models.CharField(max_length=20, choices=ContractType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    signed_date = models.DateField(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notice_period_days = models.PositiveIntegerField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    currency = models.CharField(max_length=3, default="PKR")
    status = models.CharField(
        max_length=30, choices=ContractStatus.choices, default=ContractStatus.DRAFT
    )
    client_reference = models.CharField(max_length=100, blank=True)
    purchase_order_reference = models.CharField(max_length=100, blank=True)
    internal_reference = models.CharField(max_length=100, blank=True)
    primary_client_contact = models.ForeignKey(
        ClientContact, null=True, blank=True, on_delete=models.PROTECT
    )
    account_manager = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_service_contracts"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_service_contracts",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    terminated_at = models.DateTimeField(null=True, blank=True)
    termination_reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "contract_number"], name="uniq_contract_number_company"
            )
        ]
        permissions = [
            ("approve_contract", "Can approve contracts"),
            ("activate_contract", "Can activate contracts"),
            ("terminate_contract", "Can terminate contracts"),
            ("renew_contract", "Can renew contracts"),
        ]

    @property
    def is_expired(self) -> bool:
        return self.end_date is not None and self.end_date < timezone.localdate()

    @property
    def days_until_expiry(self) -> int | None:
        return None if self.end_date is None else (self.end_date - timezone.localdate()).days

    def is_expiring_soon(self, days: int = 30) -> bool:
        remaining = self.days_until_expiry
        return remaining is not None and 0 <= remaining <= days


class ContractCommercialTerms(ContractModel):
    contract = models.OneToOneField(
        ServiceContract, on_delete=models.PROTECT, related_name="commercial_terms"
    )
    billing_frequency = models.CharField(max_length=20)
    agreed_contract_value = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    monthly_service_value = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    payment_terms_days = models.PositiveIntegerField(null=True, blank=True)
    security_deposit = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        permissions = [
            ("view_commercial_terms", "Can view commercial contract terms"),
            ("manage_commercial_terms", "Can manage commercial contract terms"),
        ]


class ContractAmendment(UUIDModel):
    contract = models.ForeignKey(
        ServiceContract, on_delete=models.PROTECT, related_name="amendments"
    )
    amendment_number = models.PositiveIntegerField()
    effective_date = models.DateField()
    title = models.CharField(max_length=200)
    description = models.TextField()
    change_type = models.CharField(max_length=20, choices=ContractChangeType.choices)
    previous_end_date = models.DateField(null=True, blank=True)
    revised_end_date = models.DateField(null=True, blank=True)
    previous_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    revised_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="approved_contract_amendments"
    )
    approved_at = models.DateTimeField()
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_contract_amendments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "amendment_number"], name="uniq_contract_amendment_number"
            )
        ]


class ContractService(ContractModel, ActiveModel):
    contract = models.ForeignKey(ServiceContract, on_delete=models.PROTECT, related_name="services")
    service_type = models.CharField(max_length=30, choices=ServiceType.choices)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)


class SiteType(ContractModel, ActiveModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_security_site_type")
        ]


class SecuritySite(ContractModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="security_sites")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="sites")
    contract = models.ForeignKey(ServiceContract, on_delete=models.PROTECT, related_name="sites")
    site_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    site_type = models.ForeignKey(SiteType, null=True, blank=True, on_delete=models.PROTECT)
    managing_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name="managed_security_sites"
    )
    operational_zone = models.ForeignKey(
        OperationalZone, null=True, blank=True, on_delete=models.PROTECT
    )
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city_name = models.CharField(max_length=100)
    province_or_state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=2, default="PK")
    timezone = models.CharField(max_length=50, default="Asia/Karachi")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_meters = models.PositiveIntegerField(null=True, blank=True)
    risk_level = models.CharField(max_length=10, choices=SiteRiskLevel.choices)
    status = models.CharField(max_length=30, choices=SiteStatus.choices, default=SiteStatus.PLANNED)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    primary_contact = models.ForeignKey(
        ClientContact, null=True, blank=True, on_delete=models.PROTECT
    )
    emergency_phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "site_code"], name="uniq_security_site_code"
            ),
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90),
                name="security_site_latitude_range",
            ),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180),
                name="security_site_longitude_range",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.site_code = self.site_code.strip().upper()
        super().save(*args, **kwargs)


class SiteContact(ContractModel, ActiveModel):
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT, related_name="contacts")
    client_contact = models.ForeignKey(
        ClientContact, null=True, blank=True, on_delete=models.PROTECT
    )
    name = models.CharField(max_length=200)
    designation = models.CharField(max_length=150, blank=True)
    mobile_number = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    contact_type = models.CharField(max_length=20, choices=ContactType.choices)


class SiteOperationalProfile(ContractModel):
    site = models.OneToOneField(
        SecuritySite, on_delete=models.PROTECT, related_name="operational_profile"
    )
    operating_hours_notes = models.TextField(blank=True)
    access_control_notes = models.TextField(blank=True)
    emergency_procedure_notes = models.TextField(blank=True)
    reporting_instructions = models.TextField(blank=True)
    uniform_requirements = models.TextField(blank=True)
    equipment_notes = models.TextField(blank=True)
    visitor_handling_notes = models.TextField(blank=True)
    prohibited_actions_notes = models.TextField(blank=True)
    escalation_notes = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        permissions = [
            ("manage_site_operational_profile", "Can manage sensitive site operational profiles")
        ]


class PostType(ContractModel, ActiveModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)


class SecurityPost(ContractModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT, related_name="posts")
    post_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location_description = models.TextField(blank=True)
    risk_level = models.CharField(max_length=10, choices=SiteRiskLevel.choices, blank=True)
    post_type = models.ForeignKey(PostType, null=True, blank=True, on_delete=models.PROTECT)
    requires_supervisor = models.BooleanField(default=False)
    is_armed_post = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=PostStatus.choices, default=PostStatus.PLANNED)
    sort_order = models.PositiveIntegerField(default=0)
    instructions = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "post_code"], name="uniq_security_post_code")
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.post_code = self.post_code.strip().upper()
        super().save(*args, **kwargs)


class PostQualificationRequirement(ContractModel, ActiveModel):
    post = models.ForeignKey(
        SecurityPost, on_delete=models.PROTECT, related_name="qualification_requirements"
    )
    qualification_type = models.ForeignKey(QualificationType, on_delete=models.PROTECT)
    requirement_level = models.CharField(max_length=20, choices=RequirementLevel.choices)
    minimum_level = models.CharField(max_length=100, blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)


class PostCredentialRequirement(ContractModel, ActiveModel):
    post = models.ForeignKey(
        SecurityPost, on_delete=models.PROTECT, related_name="credential_requirements"
    )
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    requirement_level = models.CharField(max_length=20, choices=RequirementLevel.choices)
    must_be_verified = models.BooleanField(default=True)
    must_be_unexpired = models.BooleanField(default=True)


class StaffingRequirement(ContractModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    contract = models.ForeignKey(
        ServiceContract, on_delete=models.PROTECT, related_name="staffing_requirements"
    )
    site = models.ForeignKey(
        SecuritySite, on_delete=models.PROTECT, related_name="staffing_requirements"
    )
    post = models.ForeignKey(
        SecurityPost, on_delete=models.PROTECT, related_name="staffing_requirements"
    )
    requirement_code = models.CharField(max_length=50)
    employee_type = models.CharField(max_length=20, choices=EmployeeType.choices)
    designation = models.ForeignKey(
        "organization.Designation", null=True, blank=True, on_delete=models.PROTECT
    )
    required_headcount = models.PositiveIntegerField()
    coverage_type = models.CharField(max_length=20, choices=CoverageType.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    crosses_midnight = models.BooleanField(default=False)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=StaffingRequirementStatus.choices,
        default=StaffingRequirementStatus.DRAFT,
    )
    armed_required = models.BooleanField(default=False)
    supervisor_required = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "requirement_code"], name="uniq_staffing_requirement_code"
            ),
            models.CheckConstraint(
                condition=Q(required_headcount__gt=0), name="staffing_headcount_positive"
            ),
        ]


class StaffingRequirementDay(UUIDModel):
    staffing_requirement = models.ForeignKey(
        StaffingRequirement, on_delete=models.PROTECT, related_name="days"
    )
    weekday = models.CharField(max_length=10, choices=Weekday.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["staffing_requirement", "weekday"], name="uniq_staffing_requirement_day"
            )
        ]


class StaffingRequirementRevision(UUIDModel):
    staffing_requirement = models.ForeignKey(
        StaffingRequirement, on_delete=models.PROTECT, related_name="revisions"
    )
    revision_number = models.PositiveIntegerField()
    effective_from = models.DateField()
    previous_headcount = models.PositiveIntegerField()
    new_headcount = models.PositiveIntegerField()
    reason = models.TextField()
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class ServiceLevelAgreement(ContractModel, ActiveModel):
    contract = models.ForeignKey(ServiceContract, on_delete=models.PROTECT, related_name="slas")
    site = models.ForeignKey(
        SecuritySite, null=True, blank=True, on_delete=models.PROTECT, related_name="slas"
    )
    sla_type = models.CharField(max_length=30, choices=SLAType.choices)
    name = models.CharField(max_length=200)
    description = models.TextField()
    target_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    target_unit = models.CharField(max_length=20)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)


class SiteEscalationContact(ContractModel, ActiveModel):
    site = models.ForeignKey(
        SecuritySite, on_delete=models.PROTECT, related_name="escalation_contacts"
    )
    sequence = models.PositiveIntegerField()
    contact_name = models.CharField(max_length=200)
    organization = models.CharField(max_length=30)
    designation = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30)
    alternate_phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    escalation_type = models.CharField(max_length=100)
    available_24_7 = models.BooleanField(default=False)


class SiteCalendarException(UUIDModel):
    site = models.ForeignKey(
        SecuritySite, on_delete=models.PROTECT, related_name="calendar_exceptions"
    )
    date = models.DateField()
    name = models.CharField(max_length=200)
    is_closed = models.BooleanField(default=False)
    special_hours_start = models.TimeField(null=True, blank=True)
    special_hours_end = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "date"], name="uniq_site_calendar_date")
        ]
