import hashlib
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.documents.exceptions import DocumentValidationError
from dsms.documents.validators import validate_upload
from dsms.finance.services import next_document_number

from .enums import (
    AllegationStatus,
    AppealStatus,
    CaseEventType,
    HRCaseStatus,
    InvestigationStatus,
)
from .models import (
    HRCase,
    HRCaseAllegation,
    HRCaseAppeal,
    HRCaseDecision,
    HRCaseEvent,
    HRCaseEvidence,
    HRCaseSourceReference,
    HRInvestigation,
)


def _event(case: HRCase, event_type: str, actor: Any, title: str) -> None:
    HRCaseEvent.objects.create(
        hr_case=case,
        event_type=event_type,
        actor=actor,
        event_time=timezone.now(),
        title=title,
    )


@transaction.atomic
def create_hr_case(*, company: Any, category: Any, created_by: Any, **data: Any) -> HRCase:
    number = next_document_number(company=company, prefix="HRC", year=timezone.localdate().year)
    case = HRCase(
        case_number=number,
        company=company,
        category=category,
        created_by=created_by,
        priority=data.pop("priority", category.default_priority),
        confidentiality=data.pop("confidentiality", category.default_confidentiality),
        case_type=data.pop("case_type", category.case_type),
        **data,
    )
    case.full_clean()
    case.save()
    _event(case, CaseEventType.CREATED, created_by, "HR case created")
    return case


@transaction.atomic
def submit_case(*, hr_case: HRCase, actor: Any) -> HRCase:
    case = HRCase.objects.select_for_update().get(pk=hr_case.pk)
    if case.status not in {HRCaseStatus.DRAFT, HRCaseStatus.REOPENED}:
        raise ValidationError("Only draft or reopened cases can be submitted.")
    case.status = HRCaseStatus.SUBMITTED
    case.submitted_at = timezone.now()
    case.save(update_fields=["status", "submitted_at", "updated_at"])
    _event(case, CaseEventType.SUBMITTED, actor, "Case submitted for triage")
    return case


@transaction.atomic
def triage_case(*, hr_case: HRCase, actor: Any, case_manager: Any) -> HRCase:
    case = HRCase.objects.select_for_update().get(pk=hr_case.pk)
    if case.status != HRCaseStatus.SUBMITTED:
        raise ValidationError("Only submitted cases may be triaged.")
    case.status = HRCaseStatus.TRIAGE
    case.case_manager = case_manager
    case.triaged_at = timezone.now()
    case.save(update_fields=["status", "case_manager", "triaged_at", "updated_at"])
    _event(case, CaseEventType.TRIAGED, actor, "Case triaged by an authorized HR user")
    return case


@transaction.atomic
def add_allegation(*, hr_case: HRCase, actor: Any, **data: Any) -> HRCaseAllegation:
    case = HRCase.objects.select_for_update().get(pk=hr_case.pk)
    if case.status in {HRCaseStatus.CLOSED, HRCaseStatus.CANCELLED}:
        raise ValidationError("Closed or cancelled cases cannot receive allegations.")
    number = case.allegations.count() + 1
    allegation = HRCaseAllegation.objects.create(
        hr_case=case,
        allegation_number=number,
        status=AllegationStatus.OPEN,
        **data,
    )
    _event(case, CaseEventType.ALLEGATION_ADDED, actor, f"Allegation {number} added")
    return allegation


@transaction.atomic
def record_allegation_finding(
    *, allegation: HRCaseAllegation, status: str, reasoning: str, actor: Any
) -> HRCaseAllegation:
    item = (
        HRCaseAllegation.objects.select_for_update().select_related("hr_case").get(pk=allegation.pk)
    )
    final_statuses = {
        AllegationStatus.SUBSTANTIATED,
        AllegationStatus.PARTIALLY_SUBSTANTIATED,
        AllegationStatus.NOT_SUBSTANTIATED,
        AllegationStatus.INCONCLUSIVE,
        AllegationStatus.WITHDRAWN,
    }
    if status not in final_statuses or not reasoning.strip():
        raise ValidationError("A human-selected final finding requires recorded reasoning.")
    item.status = status
    item.decision_reasoning = reasoning.strip()
    item.decided_by = actor
    item.decided_at = timezone.now()
    item.save(
        update_fields=["status", "decision_reasoning", "decided_by", "decided_at", "updated_at"]
    )
    _event(
        item.hr_case,
        CaseEventType.OTHER,
        actor,
        f"Human finding recorded for allegation {item.allegation_number}",
    )
    return item


@transaction.atomic
def start_investigation(*, investigation: HRInvestigation, actor: Any) -> HRInvestigation:
    item = (
        HRInvestigation.objects.select_for_update()
        .select_related("hr_case")
        .get(pk=investigation.pk)
    )
    if item.status != InvestigationStatus.NOT_STARTED:
        raise ValidationError("Investigation has already started.")
    item.full_clean()
    item.status = InvestigationStatus.IN_PROGRESS
    item.started_at = timezone.now()
    item.save(update_fields=["status", "started_at", "updated_at"])
    item.hr_case.status = HRCaseStatus.INVESTIGATION
    item.hr_case.investigation_started_at = item.started_at
    item.hr_case.save(update_fields=["status", "investigation_started_at", "updated_at"])
    _event(item.hr_case, CaseEventType.INVESTIGATION_STARTED, actor, "Investigation started")
    return item


@transaction.atomic
def link_source(
    *,
    hr_case: HRCase,
    source_app: str,
    source_type: str,
    source_object_id: Any,
    actor: Any,
    description: str = "",
) -> HRCaseSourceReference:
    reference = HRCaseSourceReference.objects.create(
        hr_case=hr_case,
        source_app=source_app,
        source_type=source_type,
        source_object_id=source_object_id,
        linked_by=actor,
        linked_at=timezone.now(),
        description=description,
    )
    _event(hr_case, CaseEventType.OTHER, actor, "Operational source linked without modification")
    return reference


@transaction.atomic
def upload_evidence(
    *, hr_case: HRCase, upload: Any, actor: Any, title: str, evidence_type: str, **data: Any
) -> HRCaseEvidence:
    if hr_case.status in {HRCaseStatus.CLOSED, HRCaseStatus.CANCELLED}:
        raise ValidationError("Evidence cannot be added to a closed case.")
    try:
        _extension, mime_type, size = validate_upload(upload, upload.name)
    except DocumentValidationError as exc:
        raise ValidationError(exc.detail) from exc
    upload.seek(0)
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    evidence = HRCaseEvidence.objects.create(
        company=hr_case.company,
        hr_case=hr_case,
        title=title,
        evidence_type=evidence_type,
        file=upload,
        original_filename=upload.name,
        mime_type=mime_type,
        file_size=size,
        sha256_hash=digest.hexdigest(),
        collected_by=actor,
        collected_at=timezone.now(),
        **data,
    )
    _event(hr_case, CaseEventType.EVIDENCE_ADDED, actor, "Private case evidence added")
    return evidence


@transaction.atomic
def record_decision(*, hr_case: HRCase, actor: Any, **data: Any) -> HRCaseDecision:
    case = HRCase.objects.select_for_update().get(pk=hr_case.pk)
    if hasattr(case, "decision"):
        raise ValidationError("A final case decision already exists.")
    if case.created_by_id == actor.id or case.assigned_investigator_id == actor.id:
        raise ValidationError("The case maker or investigator cannot make the final decision.")
    if case.category.requires_investigation and (
        not hasattr(case, "investigation")
        or case.investigation.status != InvestigationStatus.COMPLETED
    ):
        raise ValidationError("The required human investigation is not complete.")
    decision = HRCaseDecision.objects.create(
        hr_case=case, decided_by=actor, decided_at=timezone.now(), **data
    )
    case.status = HRCaseStatus.DECIDED
    case.decided_at = decision.decided_at
    case.save(update_fields=["status", "decided_at", "updated_at"])
    _event(case, CaseEventType.DECISION_RECORDED, actor, "Human decision recorded")
    record_audit_event(
        action="HR_CASE_DECIDED",
        category=AuditCategory.HR_CASE,
        severity=AuditSeverity.HIGH,
        summary="HR case decision recorded.",
        actor_user=actor,
        company=case.company,
        branch=case.branch,
        source_object=case,
        object_reference=case.case_number,
    )
    return decision


@transaction.atomic
def decide_appeal(*, appeal: HRCaseAppeal, actor: Any, status: str, summary: str) -> HRCaseAppeal:
    item = (
        HRCaseAppeal.objects.select_for_update(of=("self",))
        .select_related("hr_case__decision")
        .get(pk=appeal.pk)
    )
    if item.status not in {AppealStatus.SUBMITTED, AppealStatus.UNDER_REVIEW}:
        raise ValidationError("Appeal is not open for decision.")
    if (
        item.hr_case.decision.decided_by_id == actor.id
        or item.appellant_employee.user_id == actor.id
    ):
        raise ValidationError("Appeal reviewer must be independent.")
    if status not in {
        AppealStatus.UPHELD,
        AppealStatus.PARTIALLY_UPHELD,
        AppealStatus.OVERTURNED,
        AppealStatus.RETURNED_FOR_REVIEW,
    }:
        raise ValidationError("Invalid human appeal decision.")
    item.status = status
    item.decision_summary = summary.strip()
    item.decided_by = actor
    item.decided_at = timezone.now()
    item.save(
        update_fields=["status", "decision_summary", "decided_by", "decided_at", "updated_at"]
    )
    _event(
        item.hr_case,
        CaseEventType.APPEAL_DECIDED,
        actor,
        "Appeal decision recorded without rewriting original decision",
    )
    record_audit_event(
        action="HR_CASE_APPEAL_DECIDED",
        category=AuditCategory.HR_CASE,
        severity=AuditSeverity.HIGH,
        summary="HR case appeal decision recorded.",
        actor_user=actor,
        company=item.hr_case.company,
        branch=item.hr_case.branch,
        source_object=item.hr_case,
        object_reference=item.hr_case.case_number,
        metadata_safe={"appeal_status": status},
    )
    return item
