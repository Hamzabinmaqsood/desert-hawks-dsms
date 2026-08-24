from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Any

from django.db.models import Q, QuerySet, Sum
from django.utils import timezone

from dsms.organization.models import Branch, Company

from .enums import ContractStatus, PostStatus, SiteStatus, StaffingRequirementStatus
from .models import Client, SecurityPost, SecuritySite, ServiceContract, StaffingRequirement


@dataclass(frozen=True)
class EffectiveStaffingDemand:
    post: SecurityPost
    required_headcount: int
    start_time: time
    end_time: time
    employee_type: str
    required_designation: Any | None
    required_qualifications: tuple[Any, ...]
    special_requirements: tuple[str, ...]
    source_contract: ServiceContract
    source_requirement: StaffingRequirement


def client_list() -> QuerySet[Client]:
    return Client.objects.select_related("company", "industry", "account_manager")


def contract_list() -> QuerySet[ServiceContract]:
    return ServiceContract.objects.select_related(
        "company", "client", "account_manager", "primary_client_contact"
    )


def security_site_list() -> QuerySet[SecuritySite]:
    return SecuritySite.objects.select_related(
        "company", "client", "contract", "managing_branch", "operational_zone", "site_type"
    )


def staffing_requirement_list() -> QuerySet[StaffingRequirement]:
    return StaffingRequirement.objects.select_related(
        "company", "contract__client", "site__managing_branch", "post", "designation"
    ).prefetch_related("days", "post__qualification_requirements", "post__credential_requirements")


def get_active_staffing_requirements(
    *,
    on_date: date,
    company: Company | None = None,
    branch: Branch | None = None,
    site: SecuritySite | None = None,
) -> QuerySet[StaffingRequirement]:
    queryset = (
        staffing_requirement_list()
        .filter(
            status__in=[StaffingRequirementStatus.ACTIVE, StaffingRequirementStatus.SUPERSEDED],
            effective_from__lte=on_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
    )
    if company:
        queryset = queryset.filter(company=company)
    if branch:
        queryset = queryset.filter(site__managing_branch=branch)
    if site:
        queryset = queryset.filter(site=site)
    return queryset


def get_effective_staffing_demand(
    *, site: SecuritySite, date: date, shift_window: tuple[time, time] | None = None
) -> tuple[EffectiveStaffingDemand, ...]:
    """Return the single authoritative, effective contract demand for a site/day."""
    requirements = get_active_staffing_requirements(on_date=date, site=site).filter(
        contract__status=ContractStatus.ACTIVE,
        site__status=SiteStatus.ACTIVE,
        post__status=PostStatus.ACTIVE,
    )
    weekday = date.strftime("%A").upper()
    requirements = requirements.filter(Q(days__isnull=True) | Q(days__weekday=weekday)).distinct()
    if shift_window:
        requirements = requirements.filter(start_time=shift_window[0], end_time=shift_window[1])
    result = []
    for requirement in requirements:
        qualifications = tuple(
            requirement.post.qualification_requirements.filter(
                is_active=True, effective_from__lte=date
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=date))
            .select_related("qualification_type")
        )
        special = tuple(
            value
            for enabled, value in (
                (requirement.armed_required, "ARMED_REQUIRED"),
                (requirement.supervisor_required, "SUPERVISOR_REQUIRED"),
            )
            if enabled
        )
        result.append(
            EffectiveStaffingDemand(
                post=requirement.post,
                required_headcount=requirement.required_headcount,
                start_time=requirement.start_time,
                end_time=requirement.end_time,
                employee_type=requirement.employee_type,
                required_designation=requirement.designation,
                required_qualifications=qualifications,
                special_requirements=special,
                source_contract=requirement.contract,
                source_requirement=requirement,
            )
        )
    return tuple(result)


def contractual_demand_summary(*, company_id: str | None = None) -> dict[str, Any]:
    today = timezone.localdate()
    requirements = get_active_staffing_requirements(on_date=today)
    contracts, sites, posts = (
        ServiceContract.objects.filter(status=ContractStatus.ACTIVE),
        SecuritySite.objects.filter(status=SiteStatus.ACTIVE),
        SecurityPost.objects.filter(status=PostStatus.ACTIVE),
    )
    if company_id:
        requirements, contracts, sites, posts = (
            requirements.filter(company_id=company_id),
            contracts.filter(company_id=company_id),
            sites.filter(company_id=company_id),
            posts.filter(company_id=company_id),
        )
    total = requirements.aggregate(value=Sum("required_headcount"))["value"] or 0
    return {
        "active_contracts": contracts.count(),
        "active_sites": sites.count(),
        "active_posts": posts.count(),
        "total_required_guard_positions": total,
        "armed_positions": requirements.filter(armed_required=True).aggregate(
            value=Sum("required_headcount")
        )["value"]
        or 0,
        "supervisor_positions": requirements.filter(supervisor_required=True).aggregate(
            value=Sum("required_headcount")
        )["value"]
        or 0,
        "demand_by_branch": list(
            requirements.values("site__managing_branch__name").annotate(
                required=Sum("required_headcount")
            )
        ),
        "demand_by_client": list(
            requirements.values("contract__client__legal_name").annotate(
                required=Sum("required_headcount")
            )
        ),
        "demand_by_site": list(
            requirements.values("site__name").annotate(required=Sum("required_headcount"))
        ),
        "demand_by_employee_type": list(
            requirements.values("employee_type").annotate(required=Sum("required_headcount"))
        ),
    }


def contract_dashboard_summary(*, company_id: str | None = None) -> dict[str, Any]:
    today = timezone.localdate()
    contracts, clients, sites, posts = (
        ServiceContract.objects.all(),
        Client.objects.all(),
        SecuritySite.objects.all(),
        SecurityPost.objects.all(),
    )
    if company_id:
        contracts, clients, sites, posts = (
            contracts.filter(company_id=company_id),
            clients.filter(company_id=company_id),
            sites.filter(company_id=company_id),
            posts.filter(company_id=company_id),
        )
    demand = contractual_demand_summary(company_id=company_id)
    return {
        "active_clients": clients.filter(status="ACTIVE").count(),
        "active_contracts": contracts.filter(status="ACTIVE").count(),
        "contracts_expiring_in_30_days": contracts.filter(
            end_date__range=(today, today + timedelta(days=30))
        ).count(),
        "contracts_expired": contracts.filter(end_date__lt=today).count(),
        "active_sites": sites.filter(status="ACTIVE").count(),
        "active_posts": posts.filter(status="ACTIVE").count(),
        "total_contractual_manpower_demand": demand["total_required_guard_positions"],
        "armed_post_demand": demand["armed_positions"],
        "supervisor_demand": demand["supervisor_positions"],
        "contracts_pending_approval": contracts.filter(status="PENDING_APPROVAL").count(),
        "sites_without_staffing_requirements": sites.filter(
            status="ACTIVE", staffing_requirements__isnull=True
        ).count(),
        "posts_without_requirements": posts.filter(
            status="ACTIVE", staffing_requirements__isnull=True
        ).count(),
    }


def get_post_requirements(post: SecurityPost) -> dict[str, Any]:
    return {
        "qualifications": post.qualification_requirements.filter(is_active=True).select_related(
            "qualification_type"
        ),
        "credentials": post.credential_requirements.filter(is_active=True).select_related(
            "document_type"
        ),
    }
