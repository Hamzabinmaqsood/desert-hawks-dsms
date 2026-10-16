from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.subscriptions.enforcement import requires_company_module

from .enums import KPIResultStatus, PerformancePlanStatus
from .models import (
    EmployeeKPIAssignment,
    EmployeePerformancePlan,
    PerformanceAcknowledgement,
    PerformanceKPIResult,
    PerformanceRatingBand,
    PerformanceTemplate,
)
from .providers import provider_registry

ZERO = Decimal("0")


def resolve_template(*, employee: Any, cycle: Any) -> PerformanceTemplate | None:
    candidates = (
        PerformanceTemplate.objects.filter(
            company=cycle.company,
            is_active=True,
            effective_from__lte=cycle.period_start,
        )
        .filter(effective_to__isnull=True)
        .order_by("-version_number")
    )
    for template in candidates:
        checks = (
            (not template.branch_id or template.branch_id == employee.branch_id),
            (not template.department_id or template.department_id == employee.department_id),
            (not template.designation_id or template.designation_id == employee.designation_id),
            (not template.employee_type or template.employee_type == employee.employee_type),
            (not template.employment_type or template.employment_type == employee.employment_type),
        )
        if all(checks):
            return template
    return None


@transaction.atomic
@requires_company_module("performance", argument="cycle")
def generate_performance_plans(
    *, cycle: Any, created_by: Any, employee_queryset: QuerySet[Any]
) -> dict[str, Any]:
    created: list[str] = []
    missing_templates: list[str] = []
    for employee in employee_queryset.select_related("branch", "department", "designation"):
        if EmployeePerformancePlan.objects.filter(employee=employee, cycle=cycle).exists():
            continue
        template = resolve_template(employee=employee, cycle=cycle)
        if template is None:
            missing_templates.append(str(employee.id))
            continue
        plan = EmployeePerformancePlan.objects.create(
            company=cycle.company,
            employee=employee,
            cycle=cycle,
            template=template,
            template_version=template.version_number,
            created_by=created_by,
        )
        created.append(str(plan.id))
    return {"created_plan_ids": created, "missing_template_employee_ids": missing_templates}


@transaction.atomic
@requires_company_module("performance", argument="plan")
def activate_plan(*, plan: EmployeePerformancePlan, actor: Any) -> EmployeePerformancePlan:
    locked = EmployeePerformancePlan.objects.select_for_update().get(pk=plan.pk)
    if locked.status != PerformancePlanStatus.DRAFT:
        raise ValidationError("Only a draft plan can be activated.")
    template_kpis = locked.template.sections.prefetch_related("kpis__kpi_definition").all()
    assignments: list[EmployeeKPIAssignment] = []
    for section in template_kpis:
        for template_kpi in section.kpis.all():
            assignments.append(
                EmployeeKPIAssignment(
                    plan=locked,
                    template_kpi=template_kpi,
                    kpi_definition=template_kpi.kpi_definition,
                    weight=template_kpi.weight,
                    target_value=template_kpi.target_value,
                    stretch_value=template_kpi.stretch_value,
                )
            )
    EmployeeKPIAssignment.objects.bulk_create(assignments)
    locked.status = PerformancePlanStatus.ACTIVE
    locked.activated_at = timezone.now()
    locked.save(update_fields=["status", "activated_at", "updated_at"])
    return locked


@transaction.atomic
@requires_company_module("performance", argument="assignment")
def calculate_kpi_result(*, assignment: EmployeeKPIAssignment, actor: Any) -> PerformanceKPIResult:
    locked = (
        EmployeeKPIAssignment.objects.select_for_update()
        .select_related("plan__employee", "plan__cycle", "kpi_definition")
        .get(pk=assignment.pk)
    )
    provider = provider_registry.get(locked.kpi_definition.data_source)
    result = provider.calculate(
        employee=locked.plan.employee,
        cycle=locked.plan.cycle,
        kpi_definition=locked.kpi_definition,
        target=locked,
    )
    item, _ = PerformanceKPIResult.objects.update_or_create(
        plan=locked.plan,
        employee_kpi_assignment=locked,
        measurement_period_start=locked.plan.cycle.period_start,
        measurement_period_end=locked.plan.cycle.period_end,
        defaults={
            "calculated_value": result.value,
            "source": locked.kpi_definition.data_source,
            "source_reference": {
                **result.source_reference,
                "source_count": result.source_count,
                "warnings": result.warnings,
            },
            "calculated_at": timezone.now(),
            "calculation_version": "1",
            "status": KPIResultStatus.CALCULATED
            if result.is_complete
            else KPIResultStatus.INCOMPLETE,
        },
    )
    return item


def calculate_score_preview(*, plan: EmployeePerformancePlan) -> dict[str, Any]:
    results = plan.kpi_results.select_related("employee_kpi_assignment__kpi_definition").filter(
        status=KPIResultStatus.FINALIZED
    )
    required_count = plan.kpi_assignments.filter(template_kpi__is_required=True).count()
    if results.count() < required_count:
        return {"score": None, "complete": False, "reason": "Required KPI results are missing."}
    numerator = denominator = ZERO
    breakdown = []
    for result in results:
        value = result.finalized_value
        weight = result.employee_kpi_assignment.weight
        if value is None:
            continue
        numerator += value * weight
        denominator += weight
        breakdown.append(
            {
                "kpi": result.employee_kpi_assignment.kpi_definition.code,
                "value": value,
                "weight": weight,
            }
        )
    return {
        "score": numerator / denominator if denominator else None,
        "complete": bool(denominator),
        "breakdown": breakdown,
    }


@transaction.atomic
@requires_company_module("performance", argument="plan")
def finalize_performance_review(
    *, plan: EmployeePerformancePlan, actor: Any, rating_scale: Any, summary: str
) -> EmployeePerformancePlan:
    locked = EmployeePerformancePlan.objects.select_for_update().get(pk=plan.pk)
    if locked.status not in {PerformancePlanStatus.FINAL_REVIEW, PerformancePlanStatus.CALIBRATION}:
        raise ValidationError("Plan is not ready for human finalization.")
    if locked.manager_user_id == actor.id or locked.employee.user_id == actor.id:
        raise ValidationError("Employee or primary manager cannot self-finalize the review.")
    preview = calculate_score_preview(plan=locked)
    score = preview["score"]
    if not preview["complete"] or score is None:
        raise ValidationError(preview.get("reason", "Required review data is incomplete."))
    band = (
        PerformanceRatingBand.objects.filter(
            scale=rating_scale, minimum_score__lte=score, maximum_score__gte=score
        )
        .order_by("sort_order")
        .first()
    )
    if band is None:
        raise ValidationError("No configured rating band contains the final score.")
    locked.final_score = score
    locked.final_rating_band = band
    locked.final_summary = summary.strip()
    locked.finalized_at = timezone.now()
    locked.status = PerformancePlanStatus.COMPLETED
    locked.save(
        update_fields=[
            "final_score",
            "final_rating_band",
            "final_summary",
            "finalized_at",
            "status",
            "updated_at",
        ]
    )
    record_audit_event(
        action="PERFORMANCE_REVIEW_FINALIZED",
        category=AuditCategory.PERFORMANCE,
        severity=AuditSeverity.HIGH,
        summary="Performance review human-finalized.",
        actor_user=actor,
        company=locked.company,
        source_object=locked,
    )
    return locked


@transaction.atomic
@requires_company_module("performance", argument="plan")
def acknowledge_review(
    *, plan: EmployeePerformancePlan, employee: Any, agrees: bool | None, comments: str
) -> PerformanceAcknowledgement:
    locked = EmployeePerformancePlan.objects.select_for_update().get(pk=plan.pk)
    if locked.employee_id != employee.id or locked.status != PerformancePlanStatus.COMPLETED:
        raise ValidationError("Only the plan employee may acknowledge a completed review.")
    acknowledgement = PerformanceAcknowledgement.objects.create(
        plan=locked,
        employee=employee,
        acknowledged_at=timezone.now(),
        agrees_with_review=agrees,
        comments=comments,
    )
    locked.status = PerformancePlanStatus.ACKNOWLEDGED
    locked.acknowledged_at = acknowledgement.acknowledged_at
    locked.save(update_fields=["status", "acknowledged_at", "updated_at"])
    return acknowledgement
