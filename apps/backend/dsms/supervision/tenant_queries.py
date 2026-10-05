# mypy: disable-error-code="no-untyped-def,no-any-return,no-untyped-call,operator"
"""Explicit tenant-consistency predicates for Supervision projections."""

from __future__ import annotations

from django.db.models import F, Q, QuerySet
from django.utils import timezone

from dsms.attendance.models import AttendanceRecord
from dsms.attendance.tenant_queries import (
    consistent_attendance_records,
    consistent_duty_assignments,
)
from dsms.deployment.models import DutyAssignment
from dsms.identity import access

from .models import (
    CorrectiveAction,
    FieldEvidence,
    GuardObservation,
    InspectionFinding,
    InspectionResponse,
    InspectionTemplate,
    SiteInspection,
    SiteObservation,
    SiteVisit,
    SiteVisitClientFeedback,
    SupervisionAssignment,
    SupervisorDailyReport,
    SupervisorVisitPlan,
    VisitFrequencyRequirement,
)


def _active_company(queryset):
    return queryset.filter(company__is_active=True)


def consistent_assignments(
    queryset: QuerySet[SupervisionAssignment],
) -> QuerySet[SupervisionAssignment]:
    return (
        _active_company(queryset)
        .filter(supervisor__company_id=F("company_id"))
        .filter(
            Q(supervisor__branch__isnull=True) | Q(supervisor__branch__company_id=F("company_id"))
        )
        .filter(branch__company_id=F("company_id"))
        .filter(Q(operational_zone__isnull=True) | Q(operational_zone__company_id=F("company_id")))
        .filter(Q(operational_zone__isnull=True) | Q(operational_zone__branch_id=F("branch_id")))
        .filter(Q(site__isnull=True) | Q(site__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__client__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__contract__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__managing_branch_id=F("branch_id")))
        .filter(
            Q(site__isnull=True)
            | Q(operational_zone__isnull=True)
            | Q(site__operational_zone_id=F("operational_zone_id"))
        )
    )


def consistent_frequency_requirements(
    queryset: QuerySet[VisitFrequencyRequirement],
) -> QuerySet[VisitFrequencyRequirement]:
    return (
        _active_company(queryset)
        .filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id")))
        .filter(Q(operational_zone__isnull=True) | Q(operational_zone__company_id=F("company_id")))
        .filter(
            Q(branch__isnull=True)
            | Q(operational_zone__isnull=True)
            | Q(operational_zone__branch_id=F("branch_id"))
        )
        .filter(Q(site__isnull=True) | Q(site__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__client__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__contract__company_id=F("company_id")))
        .filter(
            Q(branch__isnull=True)
            | Q(site__isnull=True)
            | Q(site__managing_branch_id=F("branch_id"))
        )
        .filter(
            Q(operational_zone__isnull=True)
            | Q(site__isnull=True)
            | Q(site__operational_zone_id=F("operational_zone_id"))
        )
    )


def consistent_visit_plans(
    queryset: QuerySet[SupervisorVisitPlan],
) -> QuerySet[SupervisorVisitPlan]:
    return (
        _active_company(queryset)
        .filter(supervisor__company_id=F("company_id"))
        .filter(
            Q(supervisor__branch__isnull=True) | Q(supervisor__branch__company_id=F("company_id"))
        )
        .filter(branch__company_id=F("company_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__client__company_id=F("company_id"))
        .filter(site__contract__company_id=F("company_id"))
        .filter(site__managing_branch_id=F("branch_id"))
        .filter(
            Q(supervision_assignment__isnull=True)
            | Q(supervision_assignment__company_id=F("company_id"))
        )
        .filter(
            Q(supervision_assignment__isnull=True)
            | Q(supervision_assignment__supervisor_id=F("supervisor_id"))
        )
        .filter(
            Q(supervision_assignment__isnull=True)
            | Q(supervision_assignment__branch_id=F("branch_id"))
        )
        .filter(
            Q(generated_from_requirement__isnull=True)
            | Q(generated_from_requirement__company_id=F("company_id"))
        )
    )


def consistent_site_visits(queryset: QuerySet[SiteVisit]) -> QuerySet[SiteVisit]:
    return (
        _active_company(queryset)
        .filter(supervisor__company_id=F("company_id"))
        .filter(
            Q(supervisor__branch__isnull=True) | Q(supervisor__branch__company_id=F("company_id"))
        )
        .filter(branch__company_id=F("company_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__client__company_id=F("company_id"))
        .filter(site__contract__company_id=F("company_id"))
        .filter(site__managing_branch_id=F("branch_id"))
        .filter(Q(visit_plan__isnull=True) | Q(visit_plan__company_id=F("company_id")))
        .filter(Q(visit_plan__isnull=True) | Q(visit_plan__supervisor_id=F("supervisor_id")))
        .filter(Q(visit_plan__isnull=True) | Q(visit_plan__site_id=F("site_id")))
        .filter(Q(visit_plan__isnull=True) | Q(visit_plan__branch_id=F("branch_id")))
    )


def consistent_templates(
    queryset: QuerySet[InspectionTemplate],
) -> QuerySet[InspectionTemplate]:
    return (
        queryset.filter(Q(company__isnull=True) | Q(company__is_active=True))
        .filter(
            Q(site_type__isnull=True)
            | Q(site_type__company__isnull=True)
            | Q(company__isnull=False, site_type__company_id=F("company_id"))
        )
        .filter(
            Q(designation__isnull=True)
            | Q(company__isnull=False, designation__company_id=F("company_id"))
        )
    )


def consistent_inspections(
    queryset: QuerySet[SiteInspection],
) -> QuerySet[SiteInspection]:
    return (
        _active_company(queryset)
        .filter(site_visit__in=consistent_site_visits(SiteVisit.objects.all()))
        .filter(site_visit__company_id=F("company_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__client__company_id=F("company_id"))
        .filter(site__contract__company_id=F("company_id"))
        .filter(site_id=F("site_visit__site_id"))
        .filter(Q(post__isnull=True) | Q(post__company_id=F("company_id")))
        .filter(Q(post__isnull=True) | Q(post__site_id=F("site_id")))
        .filter(Q(post__isnull=True) | Q(post__client_id=F("site__client_id")))
        .filter(
            Q(inspected_employee__isnull=True) | Q(inspected_employee__company_id=F("company_id"))
        )
        .filter(
            Q(inspected_employee__isnull=True)
            | Q(inspected_employee__branch__isnull=True)
            | Q(inspected_employee__branch__company_id=F("company_id"))
        )
        .filter(Q(template__company__isnull=True) | Q(template__company_id=F("company_id")))
        .filter(template__in=consistent_templates(InspectionTemplate.objects.all()))
    )


def consistent_responses(
    queryset: QuerySet[InspectionResponse],
) -> QuerySet[InspectionResponse]:
    return (
        queryset.filter(inspection__in=consistent_inspections(SiteInspection.objects.all()))
        .filter(template_item__section__template_id=F("inspection__template_id"))
        .filter(Q(selected_option__isnull=True) | Q(selected_option__item_id=F("template_item_id")))
    )


def consistent_guard_observations(
    queryset: QuerySet[GuardObservation],
) -> QuerySet[GuardObservation]:
    return (
        _active_company(queryset)
        .filter(site_visit__in=consistent_site_visits(SiteVisit.objects.all()))
        .filter(site_visit__company_id=F("company_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__client__company_id=F("company_id"))
        .filter(site__contract__company_id=F("company_id"))
        .filter(site_id=F("site_visit__site_id"))
        .filter(post__company_id=F("company_id"))
        .filter(post__site_id=F("site_id"))
        .filter(post__client_id=F("site__client_id"))
        .filter(Q(employee__isnull=True) | Q(employee__company_id=F("company_id")))
        .filter(
            Q(employee__isnull=True)
            | Q(employee__branch__isnull=True)
            | Q(employee__branch__company_id=F("company_id"))
        )
        .filter(
            Q(expected_duty_assignment__isnull=True)
            | Q(
                expected_duty_assignment__in=consistent_duty_assignments(
                    DutyAssignment.objects.all()
                )
            )
        )
        .filter(
            Q(expected_duty_assignment__isnull=True)
            | Q(expected_duty_assignment__duty_shift__site_id=F("site_id"))
        )
        .filter(
            Q(expected_duty_assignment__isnull=True)
            | Q(expected_duty_assignment__duty_shift__post_id=F("post_id"))
        )
        .filter(
            Q(attendance_record__isnull=True)
            | Q(attendance_record__in=consistent_attendance_records(AttendanceRecord.objects.all()))
        )
        .filter(
            Q(attendance_record__isnull=True) | Q(attendance_record__company_id=F("company_id"))
        )
        .filter(Q(attendance_record__isnull=True) | Q(expected_duty_assignment__isnull=False))
        .filter(
            Q(attendance_record__isnull=True)
            | Q(attendance_record__duty_assignment_id=F("expected_duty_assignment_id"))
        )
    )


def consistent_findings(
    queryset: QuerySet[InspectionFinding],
) -> QuerySet[InspectionFinding]:
    return (
        _active_company(queryset)
        .filter(inspection__in=consistent_inspections(SiteInspection.objects.all()))
        .filter(inspection__company_id=F("company_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__client__company_id=F("company_id"))
        .filter(site__contract__company_id=F("company_id"))
        .filter(site_id=F("inspection__site_id"))
        .filter(Q(post__isnull=True) | Q(post__company_id=F("company_id")))
        .filter(Q(post__isnull=True) | Q(post__site_id=F("site_id")))
        .filter(Q(post__isnull=True) | Q(post__client_id=F("site__client_id")))
        .filter(Q(employee__isnull=True) | Q(employee__company_id=F("company_id")))
        .filter(
            Q(employee__isnull=True)
            | Q(employee__branch__isnull=True)
            | Q(employee__branch__company_id=F("company_id"))
        )
        .filter(
            Q(template_item__isnull=True)
            | Q(template_item__section__template_id=F("inspection__template_id"))
        )
    )


def consistent_corrective_actions(
    queryset: QuerySet[CorrectiveAction],
) -> QuerySet[CorrectiveAction]:
    now = timezone.now()
    return (
        _active_company(queryset)
        .filter(finding__in=consistent_findings(InspectionFinding.objects.all()))
        .filter(finding__company_id=F("company_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__client__company_id=F("company_id"))
        .filter(site__contract__company_id=F("company_id"))
        .filter(site_id=F("finding__site_id"))
        .filter(Q(post__isnull=True) | Q(post__company_id=F("company_id")))
        .filter(Q(post__isnull=True) | Q(post__site_id=F("site_id")))
        .filter(Q(post__isnull=True) | Q(post__client_id=F("site__client_id")))
        .filter(
            Q(assigned_to_employee__isnull=True)
            | Q(assigned_to_employee__company_id=F("company_id"))
        )
        .filter(
            Q(assigned_to_employee__isnull=True)
            | Q(assigned_to_employee__branch__isnull=True)
            | Q(assigned_to_employee__branch__company_id=F("company_id"))
        )
        .filter(
            Q(assigned_to_user__isnull=True)
            | Q(assigned_to_user__is_superuser=True)
            | Q(assigned_to_user__employee__company_id=F("company_id"))
            | Q(
                assigned_to_user__role_assignments__company_id=F("company_id"),
                assigned_to_user__role_assignments__is_active=True,
                assigned_to_user__role_assignments__starts_at__isnull=True,
                assigned_to_user__role_assignments__ends_at__isnull=True,
            )
            | Q(
                assigned_to_user__role_assignments__company_id=F("company_id"),
                assigned_to_user__role_assignments__is_active=True,
                assigned_to_user__role_assignments__starts_at__lte=now,
                assigned_to_user__role_assignments__ends_at__isnull=True,
            )
            | Q(
                assigned_to_user__role_assignments__company_id=F("company_id"),
                assigned_to_user__role_assignments__is_active=True,
                assigned_to_user__role_assignments__starts_at__isnull=True,
                assigned_to_user__role_assignments__ends_at__gt=now,
            )
            | Q(
                assigned_to_user__role_assignments__company_id=F("company_id"),
                assigned_to_user__role_assignments__is_active=True,
                assigned_to_user__role_assignments__starts_at__lte=now,
                assigned_to_user__role_assignments__ends_at__gt=now,
            )
        )
        .distinct()
    )


def consistent_site_observations(
    queryset: QuerySet[SiteObservation],
) -> QuerySet[SiteObservation]:
    return (
        queryset.filter(site_visit__in=consistent_site_visits(SiteVisit.objects.all()))
        .filter(site__company_id=F("site_visit__company_id"))
        .filter(site_id=F("site_visit__site_id"))
        .filter(Q(post__isnull=True) | Q(post__company_id=F("site_visit__company_id")))
        .filter(Q(post__isnull=True) | Q(post__site_id=F("site_id")))
    )


def consistent_client_feedback(
    queryset: QuerySet[SiteVisitClientFeedback],
) -> QuerySet[SiteVisitClientFeedback]:
    return queryset.filter(site_visit__in=consistent_site_visits(SiteVisit.objects.all()))


def consistent_daily_reports(
    queryset: QuerySet[SupervisorDailyReport],
) -> QuerySet[SupervisorDailyReport]:
    return (
        _active_company(queryset)
        .filter(supervisor__company_id=F("company_id"))
        .filter(
            Q(supervisor__branch__isnull=True) | Q(supervisor__branch__company_id=F("company_id"))
        )
        .filter(branch__company_id=F("company_id"))
    )


def consistent_evidence(queryset: QuerySet[FieldEvidence]) -> QuerySet[FieldEvidence]:
    return (
        _active_company(queryset)
        .filter(
            Q(site_visit__isnull=False)
            | Q(inspection__isnull=False)
            | Q(finding__isnull=False)
            | Q(corrective_action__isnull=False)
        )
        .filter(Q(site_visit__isnull=True) | Q(site_visit__company_id=F("company_id")))
        .filter(
            Q(site_visit__isnull=True)
            | Q(site_visit__in=consistent_site_visits(SiteVisit.objects.all()))
        )
        .filter(Q(inspection__isnull=True) | Q(inspection__company_id=F("company_id")))
        .filter(
            Q(inspection__isnull=True)
            | Q(inspection__in=consistent_inspections(SiteInspection.objects.all()))
        )
        .filter(Q(finding__isnull=True) | Q(finding__company_id=F("company_id")))
        .filter(
            Q(finding__isnull=True)
            | Q(finding__in=consistent_findings(InspectionFinding.objects.all()))
        )
        .filter(
            Q(corrective_action__isnull=True) | Q(corrective_action__company_id=F("company_id"))
        )
        .filter(
            Q(corrective_action__isnull=True)
            | Q(corrective_action__in=consistent_corrective_actions(CorrectiveAction.objects.all()))
        )
        .filter(
            Q(site_visit__isnull=True)
            | Q(inspection__isnull=True)
            | Q(inspection__site_visit_id=F("site_visit_id"))
        )
        .filter(
            Q(inspection__isnull=True)
            | Q(finding__isnull=True)
            | Q(finding__inspection_id=F("inspection_id"))
        )
        .filter(
            Q(finding__isnull=True)
            | Q(corrective_action__isnull=True)
            | Q(corrective_action__finding_id=F("finding_id"))
        )
    )


CONSISTENCY_FILTERS = {
    SupervisionAssignment: consistent_assignments,
    VisitFrequencyRequirement: consistent_frequency_requirements,
    SupervisorVisitPlan: consistent_visit_plans,
    SiteVisit: consistent_site_visits,
    InspectionTemplate: consistent_templates,
    SiteInspection: consistent_inspections,
    InspectionResponse: consistent_responses,
    GuardObservation: consistent_guard_observations,
    InspectionFinding: consistent_findings,
    CorrectiveAction: consistent_corrective_actions,
    FieldEvidence: consistent_evidence,
    SiteObservation: consistent_site_observations,
    SiteVisitClientFeedback: consistent_client_feedback,
    SupervisorDailyReport: consistent_daily_reports,
}


def consistent_queryset(queryset):
    return CONSISTENCY_FILTERS[queryset.model](queryset)


def scoped_queryset(queryset, *, user, permission: str):
    queryset = consistent_queryset(queryset).order_by("pk")
    if user.is_superuser:
        return queryset
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    model = queryset.model
    if model is InspectionTemplate:
        return queryset.filter(Q(company__isnull=True) | Q(company_id__in=company_ids))
    if model is VisitFrequencyRequirement:
        return queryset.filter(
            Q(branch_id__in=branch_ids) | Q(branch__isnull=True, company_id__in=company_ids)
        )
    if model in {SupervisionAssignment, SupervisorVisitPlan, SiteVisit, SupervisorDailyReport}:
        return queryset.filter(branch_id__in=branch_ids)
    if model in {SiteInspection, GuardObservation, InspectionFinding, CorrectiveAction}:
        return queryset.filter(site__managing_branch_id__in=branch_ids)
    if model is InspectionResponse:
        return queryset.filter(inspection__site__managing_branch_id__in=branch_ids)
    if model is SiteObservation:
        return queryset.filter(site__managing_branch_id__in=branch_ids)
    if model is SiteVisitClientFeedback:
        return queryset.filter(site_visit__branch_id__in=branch_ids)
    if model is FieldEvidence:
        return queryset.filter(
            Q(site_visit__branch_id__in=branch_ids)
            | Q(inspection__site__managing_branch_id__in=branch_ids)
            | Q(finding__site__managing_branch_id__in=branch_ids)
            | Q(corrective_action__site__managing_branch_id__in=branch_ids)
        ).distinct()
    return queryset.none()
