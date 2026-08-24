from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from dsms.identity import access

from .enums import CaseConfidentiality
from .models import HRCase


def accessible_hr_cases(*, user: Any) -> QuerySet[HRCase]:
    company_ids = access.get_accessible_company_ids(user, permission="hr_cases.view_hrcase")
    branch_ids = access.get_accessible_branch_ids(user, permission="hr_cases.view_hrcase")
    department_ids = access.get_accessible_department_ids(user, permission="hr_cases.view_hrcase")
    qs = HRCase.objects.filter(company_id__in=company_ids).filter(
        Q(branch__isnull=True) | Q(branch_id__in=branch_ids) | Q(department_id__in=department_ids)
    )
    grants = Q(
        access_grants__user=user,
        access_grants__revoked_at__isnull=True,
    ) & (
        Q(access_grants__expires_at__isnull=True) | Q(access_grants__expires_at__gt=timezone.now())
    )
    if not user.has_perm("hr_cases.view_highly_confidential_case"):
        qs = qs.exclude(confidentiality=CaseConfidentiality.HIGHLY_CONFIDENTIAL).union(
            HRCase.objects.filter(grants)
        )
    if not user.has_perm("hr_cases.view_confidential_case"):
        qs = qs.filter(confidentiality=CaseConfidentiality.STANDARD).union(
            HRCase.objects.filter(grants)
        )
    return qs.select_related(
        "company", "category", "employee_subject", "branch", "department"
    ).distinct()


def own_disclosed_cases(*, employee: Any) -> QuerySet[HRCase]:
    return (
        HRCase.objects.filter(employee_subject=employee)
        .exclude(status="DRAFT")
        .only("id", "case_number", "case_type", "title", "status", "reported_at")
    )
