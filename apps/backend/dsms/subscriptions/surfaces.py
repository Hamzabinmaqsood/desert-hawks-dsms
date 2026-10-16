"""Accountability metadata for backend entitlement enforcement surfaces.

Runtime authorization stays explicit on each view, service, and task.  This
module gives tests a deliberately small inventory of exemptions and registered
background work so new backend surfaces cannot silently avoid classification.
"""

from __future__ import annotations

from typing import Final, Literal

SurfaceKind = Literal["CORE", "INTERNAL_PLATFORM"]

# These applications expose tenant administration or infrastructure required
# regardless of the commercial module set.  The tuple is intentionally exact
# rather than URL-prefix based because mixed applications are module-gated at
# their individual views.
ROUTE_MODULE_EXEMPTIONS: Final[dict[str, SurfaceKind]] = {
    "dsms.audit.api.views": "CORE",
    "dsms.common.views": "CORE",
    "dsms.identity.api.auth_views": "CORE",
    "dsms.identity.api.views": "CORE",
    "dsms.notifications.api.views": "CORE",
    "dsms.organization.api.views": "CORE",
    "dsms.organization.api.provisioning_views": "INTERNAL_PLATFORM",
    "dsms.organization.api.platform_views": "INTERNAL_PLATFORM",
    "dsms.subscriptions.api.views": "INTERNAL_PLATFORM",
}

INTERNAL_PLATFORM_VIEW_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "dsms.finance.api.domain_views.DomainCollectionView",
        "dsms.finance.api.domain_views.DomainDetailView",
        "dsms.finance.api.domain_views.FinanceActionView",
    }
)

# The accepted Celery inventory has twelve project tasks.  CORE means transport
# lifecycle only; module entries are rechecked at task execution.
TASK_SURFACE_MANIFEST: Final[dict[str, str | SurfaceKind]] = {
    "dsms.attendance.tasks.detect_attendance_missing_checkout": "attendance",
    "dsms.billing.tasks.generate_recurring_billing_drafts": "billing_receivables",
    "dsms.billing.tasks.queue_overdue_collection_reminders": "billing_receivables",
    "dsms.finance.tasks.generate_recurring_expense_drafts": "finance_core",
    "dsms.finance.payment_tasks.process_payment_instruction_task": "ORIGIN_DERIVED",
    "dsms.finance.payment_tasks.process_payment_batch_task": "ORIGIN_DERIVED",
    "dsms.incidents.tasks.reconcile_incident_slas": "security_incidents",
    "dsms.patrol.tasks.detect_missed_patrol_tasks": "security_patrol",
    "dsms.supervision.tasks.detect_overdue_corrective_actions": "security_supervision",
    "dsms.notifications.tasks.process_notification_event_task": "CORE",
    "dsms.notifications.tasks.process_pending_notification_events": "CORE",
    "dsms.notifications.tasks.mark_expired_notifications": "CORE",
}


def exempt_route_kind(view_class: type[object]) -> SurfaceKind | None:
    path = f"{view_class.__module__}.{view_class.__name__}"
    if path in INTERNAL_PLATFORM_VIEW_CLASSES:
        return "INTERNAL_PLATFORM"
    return ROUTE_MODULE_EXEMPTIONS.get(view_class.__module__)
