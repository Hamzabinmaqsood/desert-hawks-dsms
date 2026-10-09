from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from dsms.identity.models import User

from .enums import ClientStatus, ContractStatus, PostStatus, SiteStatus, StaffingRequirementStatus
from .exceptions import (
    ContractMakerCheckerViolation,
    ContractValidationError,
    InvalidContractTransition,
)
from .models import (
    Client,
    ContractAmendment,
    SecurityPost,
    SecuritySite,
    ServiceContract,
    StaffingRequirement,
    StaffingRequirementRevision,
)


def activate_client(*, client: Client) -> Client:
    if not client.company.is_active:
        raise ContractValidationError("An inactive Company cannot activate clients.")
    client.status = ClientStatus.ACTIVE
    client.save(update_fields=["status", "updated_at"])
    return client


@transaction.atomic
def submit_contract_for_approval(*, contract: ServiceContract) -> ServiceContract:
    contract = ServiceContract.objects.select_for_update().get(pk=contract.pk)
    if contract.status != ContractStatus.DRAFT:
        raise InvalidContractTransition("Only draft contracts can be submitted.")
    if contract.contract_type == "FIXED_TERM" and not contract.end_date:
        raise ContractValidationError("Fixed-term contracts require an end date.")
    if contract.end_date and contract.end_date < contract.start_date:
        raise ContractValidationError("Contract end date cannot precede start date.")
    contract.status = ContractStatus.PENDING_APPROVAL
    contract.save(update_fields=["status", "updated_at"])
    return contract


@transaction.atomic
def approve_contract(*, contract: ServiceContract, actor: User) -> ServiceContract:
    contract = ServiceContract.objects.select_for_update().get(pk=contract.pk)
    if contract.created_by_id == actor.id and not actor.is_superuser:
        raise ContractMakerCheckerViolation("Contract creator cannot provide final approval.")
    if contract.status != ContractStatus.PENDING_APPROVAL:
        raise InvalidContractTransition("Only pending contracts can be approved.")
    contract.status, contract.approved_by, contract.approved_at = (
        ContractStatus.APPROVED,
        actor,
        timezone.now(),
    )
    contract.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return contract


@transaction.atomic
def activate_contract(*, contract: ServiceContract) -> ServiceContract:
    contract = (
        ServiceContract.objects.select_for_update()
        .select_related("client", "company")
        .get(pk=contract.pk)
    )
    if (
        contract.status != ContractStatus.APPROVED
        or contract.client.status != ClientStatus.ACTIVE
        or not contract.company.is_active
    ):
        raise InvalidContractTransition(
            "Approved contract, active client, and active company are required."
        )
    if contract.end_date and contract.end_date < timezone.localdate():
        raise ContractValidationError("An already expired contract cannot be activated.")
    contract.status, contract.activated_at = ContractStatus.ACTIVE, timezone.now()
    contract.save(update_fields=["status", "activated_at", "updated_at"])
    return contract


@transaction.atomic
def activate_security_site(*, site: SecuritySite) -> SecuritySite:
    site = SecuritySite.objects.select_for_update().select_related("contract").get(pk=site.pk)
    if site.contract.status != ContractStatus.ACTIVE:
        raise InvalidContractTransition("An active contract is required to activate a site.")
    site.status = SiteStatus.ACTIVE
    site.save(update_fields=["status", "updated_at"])
    return site


@transaction.atomic
def activate_security_post(*, post: SecurityPost) -> SecurityPost:
    post = SecurityPost.objects.select_for_update().select_related("site").get(pk=post.pk)
    if post.site.status != SiteStatus.ACTIVE:
        raise InvalidContractTransition("An active site is required to activate a post.")
    post.status = PostStatus.ACTIVE
    post.save(update_fields=["status", "updated_at"])
    return post


@transaction.atomic
def activate_staffing_requirement(*, requirement: StaffingRequirement) -> StaffingRequirement:
    requirement = (
        StaffingRequirement.objects.select_for_update()
        .select_related("contract", "site", "post")
        .get(pk=requirement.pk)
    )
    if (
        requirement.contract.status != ContractStatus.ACTIVE
        or requirement.site.status != SiteStatus.ACTIVE
        or requirement.post.status != PostStatus.ACTIVE
    ):
        raise InvalidContractTransition("Active contract, site, and post are required.")
    if requirement.coverage_type == "CUSTOM" and not requirement.days.exists():
        raise ContractValidationError("Custom coverage requires at least one weekday.")
    requirement.status = StaffingRequirementStatus.ACTIVE
    requirement.save(update_fields=["status", "updated_at"])
    return requirement


@transaction.atomic
def supersede_staffing_requirement(
    *,
    requirement: StaffingRequirement,
    new_headcount: int,
    effective_from: date,
    reason: str,
    actor: User,
) -> StaffingRequirement:
    requirement = StaffingRequirement.objects.select_for_update().get(pk=requirement.pk)
    if requirement.status != StaffingRequirementStatus.ACTIVE or new_headcount < 1:
        raise InvalidContractTransition(
            "Only an active requirement can be superseded with positive demand."
        )
    revision = (
        requirement.revisions.order_by("-revision_number")
        .values_list("revision_number", flat=True)
        .first()
        or 0
    ) + 1
    StaffingRequirementRevision.objects.create(
        staffing_requirement=requirement,
        revision_number=revision,
        effective_from=effective_from,
        previous_headcount=requirement.required_headcount,
        new_headcount=new_headcount,
        reason=reason,
        changed_by=actor,
    )
    requirement.status, requirement.effective_to = (
        StaffingRequirementStatus.SUPERSEDED,
        effective_from - timedelta(days=1),
    )
    requirement.save(update_fields=["status", "effective_to", "updated_at"])
    replacement = StaffingRequirement.objects.create(
        company=requirement.company,
        contract=requirement.contract,
        site=requirement.site,
        post=requirement.post,
        requirement_code=f"{requirement.requirement_code}-R{revision}",
        employee_type=requirement.employee_type,
        designation=requirement.designation,
        required_headcount=new_headcount,
        coverage_type=requirement.coverage_type,
        start_time=requirement.start_time,
        end_time=requirement.end_time,
        crosses_midnight=requirement.crosses_midnight,
        effective_from=effective_from,
        status=StaffingRequirementStatus.ACTIVE,
        armed_required=requirement.armed_required,
        supervisor_required=requirement.supervisor_required,
        notes=requirement.notes,
    )
    for day in requirement.days.all():
        replacement.days.create(weekday=day.weekday)
    return replacement


@transaction.atomic
def create_contract_amendment(
    *,
    contract: ServiceContract,
    effective_date: date,
    title: str,
    description: str,
    change_type: str,
    actor: User,
    approver: User,
) -> ContractAmendment:
    contract = ServiceContract.objects.select_for_update().get(pk=contract.pk)
    number = (
        contract.amendments.order_by("-amendment_number")
        .values_list("amendment_number", flat=True)
        .first()
        or 0
    ) + 1
    return ContractAmendment.objects.create(
        contract=contract,
        amendment_number=number,
        effective_date=effective_date,
        title=title,
        description=description,
        change_type=change_type,
        approved_by=approver,
        approved_at=timezone.now(),
        created_by=actor,
    )
