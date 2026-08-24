from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from dsms.audit.models import AuditEvent
from dsms.performance.enums import (
    AppraisalSectionType,
    GoalMeasurementType,
    KPIDataSource,
    KPIDirection,
    KPIResultStatus,
    PerformancePlanStatus,
)
from dsms.performance.models import (
    EmployeePerformancePlan,
    KPIDefinition,
    PerformanceCycle,
    PerformanceKPIResult,
    PerformanceRatingBand,
    PerformanceRatingScale,
    PerformanceTemplate,
    PerformanceTemplateKPI,
    PerformanceTemplateSection,
)
from dsms.performance.providers import KPIProviderRegistry, ManualKPIProvider
from dsms.performance.services import (
    acknowledge_review,
    activate_plan,
    calculate_kpi_result,
    calculate_score_preview,
    finalize_performance_review,
    generate_performance_plans,
    resolve_template,
)
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def performance_graph() -> dict[str, Any]:
    company = CompanyFactory.create()
    creator = UserFactory.create()
    employee_user = UserFactory.create()
    manager = UserFactory.create()
    employee = EmployeeFactory.create(company=company, user=employee_user)
    cycle = PerformanceCycle.objects.create(
        company=company,
        code="FY26",
        name="FY 2026",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        created_by=creator,
    )
    scale = PerformanceRatingScale.objects.create(
        company=company,
        code="FIVE",
        name="Five point",
        minimum_score=0,
        maximum_score=100,
    )
    template = PerformanceTemplate.objects.create(
        company=company,
        code="DEFAULT",
        name="Default",
        is_default=True,
        effective_from=date(2025, 1, 1),
        created_by=creator,
    )
    section = PerformanceTemplateSection.objects.create(
        template=template,
        section_type=AppraisalSectionType.KPIS,
        code="KPI",
        name="KPIs",
        weight=100,
        rating_scale=scale,
    )
    definition = KPIDefinition.objects.create(
        company=company,
        code="MANUAL",
        name="Manual KPI",
        description="Human factual input",
        data_source=KPIDataSource.MANUAL,
        measurement_type=GoalMeasurementType.NUMBER,
        direction=KPIDirection.HIGHER_IS_BETTER,
        unit="points",
    )
    template_kpi = PerformanceTemplateKPI.objects.create(
        section=section,
        kpi_definition=definition,
        weight=100,
        target_value=80,
        is_required=True,
    )
    plan = EmployeePerformancePlan.objects.create(
        company=company,
        employee=employee,
        cycle=cycle,
        template=template,
        template_version=1,
        manager_user=manager,
        created_by=creator,
    )
    return {
        "company": company,
        "creator": creator,
        "employee": employee,
        "employee_user": employee_user,
        "manager": manager,
        "cycle": cycle,
        "scale": scale,
        "template": template,
        "template_kpi": template_kpi,
        "definition": definition,
        "plan": plan,
    }


def test_manual_provider_and_registry_are_deterministic() -> None:
    graph = performance_graph()
    registry = KPIProviderRegistry()
    provider = ManualKPIProvider()
    registry.register(" manual ", provider)
    assert registry.get("MANUAL") is provider
    with pytest.raises(LookupError, match="No deterministic"):
        registry.get("missing")
    result = provider.calculate(
        employee=graph["employee"],
        cycle=graph["cycle"],
        kpi_definition=graph["definition"],
        target=object(),
    )
    assert result.value is None
    assert result.is_complete is False
    assert result.source_reference["provider"] == "MANUAL"
    assert "human-entered" in result.warnings[0]


def test_template_resolution_plan_generation_and_duplicate_skip() -> None:
    graph = performance_graph()
    employee = graph["employee"]
    cycle = graph["cycle"]
    template = graph["template"]
    assert resolve_template(employee=employee, cycle=cycle) == template

    EmployeePerformancePlan.objects.filter(pk=graph["plan"].pk).delete()
    result = generate_performance_plans(
        cycle=cycle,
        created_by=graph["creator"],
        employee_queryset=type(employee).objects.filter(pk=employee.pk),
    )
    assert len(result["created_plan_ids"]) == 1
    repeated = generate_performance_plans(
        cycle=cycle,
        created_by=graph["creator"],
        employee_queryset=type(employee).objects.filter(pk=employee.pk),
    )
    assert repeated["created_plan_ids"] == []

    PerformanceTemplate.objects.filter(company=graph["company"]).update(is_active=False)
    other = EmployeeFactory.create(company=graph["company"])
    missing = generate_performance_plans(
        cycle=cycle,
        created_by=graph["creator"],
        employee_queryset=type(other).objects.filter(pk=other.pk),
    )
    assert missing["missing_template_employee_ids"] == [str(other.id)]


def test_activate_plan_copies_template_kpis_once() -> None:
    graph = performance_graph()
    plan = activate_plan(plan=graph["plan"], actor=graph["creator"])
    assignment = plan.kpi_assignments.get()
    assert plan.status == PerformancePlanStatus.ACTIVE
    assert assignment.weight == Decimal("100")
    assert assignment.kpi_definition == graph["definition"]
    with pytest.raises(ValidationError, match="Only a draft"):
        activate_plan(plan=plan, actor=graph["creator"])


def test_manual_kpi_calculation_records_incomplete_explainability() -> None:
    graph = performance_graph()
    plan = activate_plan(plan=graph["plan"], actor=graph["creator"])
    result = calculate_kpi_result(assignment=plan.kpi_assignments.get(), actor=graph["creator"])
    assert result.status == KPIResultStatus.INCOMPLETE
    assert result.source == KPIDataSource.MANUAL
    assert result.source_reference["source_count"] == 0
    assert result.source_reference["warnings"]


def test_score_preview_missing_required_zero_weight_and_weighted_score() -> None:
    graph = performance_graph()
    plan = activate_plan(plan=graph["plan"], actor=graph["creator"])
    assignment = plan.kpi_assignments.get()
    assert calculate_score_preview(plan=plan)["complete"] is False

    result = PerformanceKPIResult.objects.create(
        plan=plan,
        employee_kpi_assignment=assignment,
        measurement_period_start=plan.cycle.period_start,
        measurement_period_end=plan.cycle.period_end,
        calculated_value=80,
        finalized_value=80,
        source=KPIDataSource.MANUAL,
        calculation_version="1",
        status=KPIResultStatus.FINALIZED,
    )
    preview = calculate_score_preview(plan=plan)
    assert preview["complete"] is True
    assert preview["score"] == Decimal("80")
    assignment.weight = 0
    assignment.save(update_fields=["weight"])
    assert calculate_score_preview(plan=plan)["complete"] is False
    result.delete()


def test_human_finalization_guards_rating_audit_and_acknowledgement() -> None:
    graph = performance_graph()
    plan = activate_plan(plan=graph["plan"], actor=graph["creator"])
    assignment = plan.kpi_assignments.get()
    PerformanceKPIResult.objects.create(
        plan=plan,
        employee_kpi_assignment=assignment,
        measurement_period_start=plan.cycle.period_start,
        measurement_period_end=plan.cycle.period_end,
        calculated_value=85,
        finalized_value=85,
        source=KPIDataSource.MANUAL,
        calculation_version="1",
        status=KPIResultStatus.FINALIZED,
    )
    with pytest.raises(ValidationError, match="not ready"):
        finalize_performance_review(
            plan=plan, actor=graph["creator"], rating_scale=graph["scale"], summary="Good"
        )
    plan.status = PerformancePlanStatus.FINAL_REVIEW
    plan.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="self-finalize"):
        finalize_performance_review(
            plan=plan, actor=graph["manager"], rating_scale=graph["scale"], summary="Good"
        )
    with pytest.raises(ValidationError, match="No configured rating"):
        finalize_performance_review(
            plan=plan, actor=graph["creator"], rating_scale=graph["scale"], summary="Good"
        )
    band = PerformanceRatingBand.objects.create(
        scale=graph["scale"],
        code="GOOD",
        label="Good",
        minimum_score=80,
        maximum_score=89,
    )
    finalized = finalize_performance_review(
        plan=plan, actor=graph["creator"], rating_scale=graph["scale"], summary="  Good  "
    )
    assert finalized.status == PerformancePlanStatus.COMPLETED
    assert finalized.final_rating_band == band
    assert finalized.final_summary == "Good"
    assert AuditEvent.objects.filter(
        action="PERFORMANCE_REVIEW_FINALIZED", source_object_id=str(plan.id)
    ).exists()

    other_employee = EmployeeFactory.create(company=graph["company"])
    with pytest.raises(ValidationError, match="Only the plan employee"):
        acknowledge_review(plan=finalized, employee=other_employee, agrees=True, comments="")
    acknowledgement = acknowledge_review(
        plan=finalized, employee=graph["employee"], agrees=True, comments="Fair"
    )
    assert acknowledgement.agrees_with_review is True
    finalized.refresh_from_db()
    assert finalized.status == PerformancePlanStatus.ACKNOWLEDGED
