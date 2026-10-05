# mypy: disable-error-code="no-untyped-def"
from django.db.models import QuerySet
from django.utils import timezone

from .models import CorrectiveAction, InspectionFinding, SiteVisit, SupervisorVisitPlan
from .tenant_queries import (
    consistent_corrective_actions,
    consistent_findings,
    consistent_site_visits,
    consistent_visit_plans,
)


def get_due_visits(*, company=None, at=None) -> QuerySet[SupervisorVisitPlan]:
    moment = at or timezone.now()
    queryset = consistent_visit_plans(
        SupervisorVisitPlan.objects.filter(
            planned_date=moment.date(), status__in=["SCHEDULED", "IN_PROGRESS"]
        ).select_related("supervisor", "site", "branch")
    )
    return queryset.filter(company=company) if company else queryset


def get_open_findings(*, company=None) -> QuerySet[InspectionFinding]:
    queryset = consistent_findings(
        InspectionFinding.objects.exclude(status__in=["CLOSED", "DISMISSED"]).select_related(
            "inspection__site_visit", "site", "post", "employee"
        )
    )
    return queryset.filter(company=company) if company else queryset


def get_overdue_corrective_actions(*, company=None, at=None) -> QuerySet[CorrectiveAction]:
    queryset = consistent_corrective_actions(
        CorrectiveAction.objects.filter(due_at__lt=at or timezone.now())
        .exclude(status__in=["VERIFIED", "CLOSED", "CANCELLED"])
        .select_related("finding", "site", "assigned_to_user", "assigned_to_employee")
    )
    return queryset.filter(company=company) if company else queryset


def get_supervision_dashboard(*, company=None) -> dict[str, int]:
    today = timezone.localdate()
    visits = consistent_site_visits(SiteVisit.objects.filter(started_at__date=today))
    plans = consistent_visit_plans(SupervisorVisitPlan.objects.filter(planned_date=today))
    findings = get_open_findings(company=company)
    if company:
        visits, plans = visits.filter(company=company), plans.filter(company=company)
    return {
        "planned_visits": plans.count(),
        "completed": visits.filter(status="COMPLETED").count(),
        "missed": plans.filter(status="MISSED").count(),
        "open_findings": findings.count(),
        "critical_findings": findings.filter(severity="CRITICAL").count(),
        "overdue_corrective_actions": get_overdue_corrective_actions(company=company).count(),
    }
