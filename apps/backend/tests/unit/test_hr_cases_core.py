from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from dsms.audit.models import AuditEvent
from dsms.hr_cases.enums import (
    AllegationStatus,
    AppealStatus,
    CaseConfidentiality,
    CaseEventType,
    HRActionType,
    HRCaseStatus,
    HRCaseType,
    InvestigationStatus,
    OutcomeFinding,
)
from dsms.hr_cases.models import (
    HRCaseAppeal,
    HRCaseCategory,
    HRCaseEvent,
    HRInvestigation,
)
from dsms.hr_cases.services import (
    add_allegation,
    create_hr_case,
    decide_appeal,
    link_source,
    record_allegation_finding,
    record_decision,
    start_investigation,
    submit_case,
    triage_case,
)
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def case_graph(*, requires_investigation: bool = False) -> dict[str, Any]:
    branch = BranchFactory.create()
    creator, manager, investigator, decision_maker, appeal_reviewer = UserFactory.create_batch(5)
    subject_user = UserFactory.create()
    subject = EmployeeFactory.create(company=branch.company, branch=branch, user=subject_user)
    category = HRCaseCategory.objects.create(
        company=branch.company,
        code="CONDUCT",
        name="Conduct",
        case_type=HRCaseType.WORKPLACE_CONDUCT,
        requires_investigation=requires_investigation,
    )
    case = create_hr_case(
        company=branch.company,
        category=category,
        created_by=creator,
        employee_subject=subject,
        branch=branch,
        title="Confidential conduct review",
        summary="Safe factual summary",
        reported_at=timezone.now(),
    )
    return {
        "branch": branch,
        "creator": creator,
        "manager": manager,
        "investigator": investigator,
        "decision_maker": decision_maker,
        "appeal_reviewer": appeal_reviewer,
        "subject": subject,
        "category": category,
        "case": case,
    }


def test_case_creation_defaults_events_submit_and_triage_guards() -> None:
    graph = case_graph()
    case = graph["case"]
    assert case.case_number.startswith("HRC-")
    assert case.case_type == HRCaseType.WORKPLACE_CONDUCT
    assert case.confidentiality == CaseConfidentiality.CONFIDENTIAL
    assert case.events.get().event_type == CaseEventType.CREATED
    submitted = submit_case(hr_case=case, actor=graph["creator"])
    assert submitted.status == HRCaseStatus.SUBMITTED
    with pytest.raises(ValidationError, match="draft or reopened"):
        submit_case(hr_case=submitted, actor=graph["creator"])
    triaged = triage_case(hr_case=submitted, actor=graph["manager"], case_manager=graph["manager"])
    assert triaged.status == HRCaseStatus.TRIAGE
    assert triaged.case_manager == graph["manager"]
    with pytest.raises(ValidationError, match="submitted"):
        triage_case(hr_case=triaged, actor=graph["manager"], case_manager=graph["manager"])


def test_allegation_human_finding_and_closed_case_guard() -> None:
    graph = case_graph()
    allegation = add_allegation(
        hr_case=graph["case"],
        actor=graph["manager"],
        category_code="POLICY",
        description="Policy allegation",
    )
    assert allegation.allegation_number == 1
    with pytest.raises(ValidationError, match="recorded reasoning"):
        record_allegation_finding(
            allegation=allegation,
            status=AllegationStatus.SUBSTANTIATED,
            reasoning=" ",
            actor=graph["decision_maker"],
        )
    finding = record_allegation_finding(
        allegation=allegation,
        status=AllegationStatus.PARTIALLY_SUBSTANTIATED,
        reasoning="  Evidence supports part of the allegation. ",
        actor=graph["decision_maker"],
    )
    assert finding.decision_reasoning == "Evidence supports part of the allegation."
    graph["case"].status = HRCaseStatus.CLOSED
    graph["case"].save(update_fields=["status"])
    with pytest.raises(ValidationError, match="Closed or cancelled"):
        add_allegation(
            hr_case=graph["case"],
            actor=graph["manager"],
            category_code="OTHER",
            description="Late allegation",
        )


def test_investigation_independence_start_and_source_link() -> None:
    graph = case_graph(requires_investigation=True)
    investigation = HRInvestigation.objects.create(
        hr_case=graph["case"],
        lead_investigator=graph["investigator"],
        terms_of_reference="Independent factual investigation",
    )
    started = start_investigation(investigation=investigation, actor=graph["manager"])
    assert started.status == InvestigationStatus.IN_PROGRESS
    graph["case"].refresh_from_db()
    assert graph["case"].status == HRCaseStatus.INVESTIGATION
    with pytest.raises(ValidationError, match="already started"):
        start_investigation(investigation=started, actor=graph["manager"])
    reference = link_source(
        hr_case=graph["case"],
        source_app="incidents",
        source_type="incident",
        source_object_id=graph["case"].id,
        actor=graph["manager"],
        description="Read-only source link",
    )
    assert reference.source_app == "incidents"
    assert HRCaseEvent.objects.filter(
        hr_case=graph["case"], title__contains="source linked"
    ).exists()


def test_decision_requires_independence_and_completed_investigation() -> None:
    graph = case_graph(requires_investigation=True)
    case = graph["case"]
    case.assigned_investigator = graph["investigator"]
    case.save(update_fields=["assigned_investigator"])
    investigation = HRInvestigation.objects.create(
        hr_case=case,
        lead_investigator=graph["investigator"],
        terms_of_reference="Terms",
    )
    payload = {
        "overall_finding": OutcomeFinding.SUBSTANTIATED,
        "decision_summary": "Independent human decision",
        "action_type": HRActionType.COUNSELLING_RECORDED,
        "action_reason": "Proportionate action",
    }
    with pytest.raises(ValidationError, match="maker or investigator"):
        record_decision(hr_case=case, actor=graph["creator"], **payload)
    with pytest.raises(ValidationError, match="not complete"):
        record_decision(hr_case=case, actor=graph["decision_maker"], **payload)
    investigation.status = InvestigationStatus.COMPLETED
    investigation.completed_at = timezone.now()
    investigation.save(update_fields=["status", "completed_at"])
    decision = record_decision(hr_case=case, actor=graph["decision_maker"], **payload)
    assert decision.decision_summary == "Independent human decision"
    case.refresh_from_db()
    assert case.status == HRCaseStatus.DECIDED
    event = AuditEvent.objects.get(action="HR_CASE_DECIDED")
    assert event.actor_user == graph["decision_maker"]
    assert event.company == graph["branch"].company
    assert event.branch == graph["branch"]
    assert event.source_object_id == str(case.id)
    with pytest.raises(ValidationError, match="already exists"):
        record_decision(hr_case=case, actor=graph["appeal_reviewer"], **payload)


def test_appeal_decision_independence_status_validation_and_audit() -> None:
    graph = case_graph()
    decision = record_decision(
        hr_case=graph["case"],
        actor=graph["decision_maker"],
        overall_finding=OutcomeFinding.NOT_SUBSTANTIATED,
        decision_summary="Original decision remains visible",
        action_type=HRActionType.NO_ACTION,
        action_reason="Evidence threshold not met",
    )
    appeal = HRCaseAppeal.objects.create(
        hr_case=graph["case"],
        appellant_employee=graph["subject"],
        grounds="Procedural review requested",
        submitted_at=timezone.now(),
    )
    with pytest.raises(ValidationError, match="independent"):
        decide_appeal(
            appeal=appeal,
            actor=decision.decided_by,
            status=AppealStatus.UPHELD,
            summary="Review",
        )
    with pytest.raises(ValidationError, match="Invalid human"):
        decide_appeal(
            appeal=appeal,
            actor=graph["appeal_reviewer"],
            status=AppealStatus.CLOSED,
            summary="Review",
        )
    decided = decide_appeal(
        appeal=appeal,
        actor=graph["appeal_reviewer"],
        status=AppealStatus.PARTIALLY_UPHELD,
        summary="  Partial procedural issue  ",
    )
    assert decided.decision_summary == "Partial procedural issue"
    assert decided.hr_case.decision == decision
    assert AuditEvent.objects.filter(
        action="HR_CASE_APPEAL_DECIDED", metadata_safe__appeal_status=AppealStatus.PARTIALLY_UPHELD
    ).exists()
    with pytest.raises(ValidationError, match="not open"):
        decide_appeal(
            appeal=decided,
            actor=graph["manager"],
            status=AppealStatus.UPHELD,
            summary="Again",
        )


def test_case_timeline_is_append_only() -> None:
    event = case_graph()["case"].events.get()
    event.title = "tamper"
    with pytest.raises(ValidationError, match="immutable"):
        event.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        event.delete()
