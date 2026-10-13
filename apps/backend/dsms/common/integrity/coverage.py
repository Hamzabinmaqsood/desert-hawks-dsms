from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IntegrityCoverageClassification(StrEnum):
    SCANNED = "SCANNED"
    NO_INDEPENDENT_TENANT_RELATION = "NO_INDEPENDENT_TENANT_RELATION"
    DATABASE_CONSTRAINED = "DATABASE_CONSTRAINED"
    DERIVED_CHILD_OWNERSHIP = "DERIVED_CHILD_OWNERSHIP"
    NON_PERSISTENT_CI_COVERAGE = "NON_PERSISTENT_CI_COVERAGE"
    OUT_OF_SCOPE_LATER_SAAS = "OUT_OF_SCOPE_LATER_SAAS"


@dataclass(frozen=True)
class TenantRelationSpec:
    model_label: str
    relation_fields: tuple[str, ...]
    check_id: str
    classification: IntegrityCoverageClassification = IntegrityCoverageClassification.SCANNED


_EXISTING_CHECKS = {
    "billing.ClientCreditNote": "billing.adjustment.invoice_company_match",
    "billing.ClientDebitNote": "billing.adjustment.invoice_company_match",
    "billing.ClientInvoice": "billing.invoice.tenant_relations",
    "deployment.EmployeeDeployment": "deployment.employee_deployment.tenant_relations",
    "documents.EmployeeDocument": "documents.employee_document.tenant_relations",
    "finance.PaymentAccountingProfile": "finance.payment_accounting_profile.account_company_match",
    "finance.PaymentVoucher": "finance.payment_voucher.tenant_relations",
    "finance.VendorBill": "finance.vendor_bill.tenant_relations",
    "identity.UserRoleAssignment": "identity.role_assignment.scope_company_match",
}
_DOMAIN_CHECKS = {
    domain: f"{domain}.tenant_relations"
    for domain in ("analytics", "assets", "attendance", "incidents", "patrol", "supervision")
}


def _spec(model_label: str, *relations: str) -> TenantRelationSpec:
    domain = model_label.partition(".")[0]
    check_id = _EXISTING_CHECKS.get(
        model_label, _DOMAIN_CHECKS.get(domain, "repository.remaining_tenant_relations")
    )
    return TenantRelationSpec(model_label, relations, check_id)


# This is intentionally explicit. Runtime scanner discovery never infers models or relations.
TENANT_RELATION_SPECS = (
    _spec("analytics.AnalyticsDataQualityIssue", "branch", "client", "site"),
    _spec("analytics.AnalyticsSnapshot", "supersedes"),
    _spec(
        "analytics.AnalyticsSnapshotValue",
        "snapshot",
        "region",
        "branch",
        "client",
        "contract",
        "site",
        "department",
    ),
    _spec("analytics.ManagementReport", "snapshot", "supersedes"),
    _spec(
        "assets.Asset",
        "item",
        "current_warehouse",
        "current_branch",
        "current_site",
        "current_employee",
        "current_vehicle",
    ),
    _spec("assets.AssetIssue", "employee", "site", "branch", "vehicle"),
    _spec("assets.AssetItem", "category"),
    _spec("assets.AssetKitTemplate", "designation", "site_type"),
    _spec("assets.AssetRequirementPolicy", "designation", "branch", "item"),
    _spec("assets.AssetStore", "branch", "operational_zone", "store_manager"),
    _spec("assets.ProcurementInventoryHandoff", "asset_item"),
    _spec("assets.ProcurementInventoryRegistration", "handoff", "destination_store"),
    _spec("assets.StockAccount", "item", "store", "branch", "site"),
    _spec("attendance.AttendancePeriod", "branch"),
    _spec("attendance.AttendancePolicy", "branch", "site", "post"),
    _spec("attendance.AttendanceQRStation", "site", "post"),
    _spec(
        "attendance.AttendanceRecord",
        "branch",
        "client",
        "site",
        "post",
        "employee",
        "attendance_period",
    ),
    _spec("audit.AuditEvent", "actor_employee", "region", "branch"),
    _spec("billing.BillingSchedule", "client", "contract"),
    _spec("billing.ClientAccountTransaction", "client", "invoice", "receipt"),
    _spec(
        "billing.ClientBillingProfile",
        "client",
        "default_revenue_account",
        "default_receivable_account",
        "default_tax_account",
        "default_discount_account",
    ),
    _spec("billing.ClientCollectionActivity", "client", "invoice"),
    _spec("billing.ClientCreditNote", "client", "invoice", "accounting_journal"),
    _spec("billing.ClientDebitNote", "client", "invoice", "accounting_journal"),
    _spec(
        "billing.ClientInvoice",
        "client",
        "contract",
        "source_billing_schedule",
        "accounting_journal",
    ),
    _spec("billing.ClientInvoiceDocument", "invoice"),
    _spec("billing.ClientReceipt", "client", "bank_account", "accounting_journal"),
    _spec("billing.TaxCode", "tax_account"),
    _spec("client_portal.ClientServiceReport", "client", "contract", "supersedes"),
    _spec("client_portal.ClientSharedAttachment", "client", "report"),
    _spec("client_portal.SLAMeasurementPeriod", "client", "contract"),
    _spec("contracts.Client", "industry", "account_manager"),
    _spec("contracts.SecurityPost", "client", "site", "post_type"),
    _spec(
        "contracts.SecuritySite",
        "client",
        "contract",
        "site_type",
        "managing_branch",
        "operational_zone",
    ),
    _spec("contracts.ServiceContract", "client", "account_manager"),
    _spec("contracts.StaffingRequirement", "contract", "site", "post", "designation"),
    _spec("deployment.DeploymentPool", "branch", "operational_zone"),
    _spec(
        "deployment.DutyShift",
        "roster_period",
        "branch",
        "client",
        "contract",
        "site",
        "post",
        "staffing_requirement",
        "shift_template",
        "designation",
    ),
    _spec(
        "deployment.EmployeeDeployment",
        "employee",
        "client",
        "contract",
        "site",
        "primary_post",
        "managing_branch",
    ),
    _spec("deployment.EmployeeScheduleBlock", "employee"),
    _spec(
        "deployment.ReplacementRequest", "duty_shift", "requested_employee", "replacement_employee"
    ),
    _spec("deployment.RosterAvailabilityConflict", "leave_request", "replacement_request"),
    _spec("deployment.RosterPeriod", "branch"),
    _spec("deployment.ShiftTemplate", "branch"),
    _spec("documents.EmployeeDocument", "employee", "document_type", "superseded_by"),
    _spec("finance.Account", "parent"),
    _spec("finance.AccountingPeriod", "fiscal_year"),
    _spec("finance.BankAccount", "ledger_account"),
    _spec("finance.Budget", "fiscal_year"),
    _spec("finance.CashAccount", "ledger_account"),
    _spec(
        "finance.CompanyExpense", "category", "branch", "department", "cost_center", "journal_entry"
    ),
    _spec("finance.CostCenter", "branch", "department"),
    _spec("finance.ExpenseCategory", "expense_account"),
    _spec("finance.ExpenseClaim", "employee", "journal_entry"),
    _spec("finance.FinanceEvent", "journal_entry", "accounting_period"),
    _spec("finance.FundTransfer", "source_account", "destination_account", "journal_entry"),
    _spec("finance.JournalEntry", "fiscal_year", "accounting_period", "reversed_by_entry"),
    _spec(
        "finance.PaymentAccountingProfile",
        "payroll_payable_account",
        "vendor_payable_account",
        "gateway_clearing_account",
        "bank_account",
        "provider_fee_account",
    ),
    _spec("finance.PaymentBatch", "payroll_run", "provider"),
    _spec("finance.PaymentBeneficiaryProfile", "employee", "vendor"),
    _spec("finance.PaymentProviderSettlement", "provider", "accounting_journal"),
    _spec("finance.PaymentVoucher", "vendor_bill", "journal_entry"),
    _spec("finance.PayrollComponent", "expense_account", "payable_account"),
    _spec("finance.PayrollRun", "payroll_period", "journal_entry"),
    _spec("finance.PettyCashFund", "custodian", "cash_account"),
    _spec("finance.PurchaseOrder", "requisition", "vendor"),
    _spec("finance.PurchaseReceipt", "purchase_order"),
    _spec("finance.PurchaseRequisition", "branch", "department", "cost_center"),
    _spec("finance.RecurringExpenseTemplate", "category", "branch", "department", "cost_center"),
    _spec("finance.StatutoryScheme", "employee_component", "employer_component"),
    _spec("finance.TaxScheme", "deduction_component"),
    _spec("finance.Vendor", "payable_account"),
    _spec("finance.VendorBill", "vendor", "purchase_order", "journal_entry"),
    _spec(
        "hr_cases.HRCase",
        "employee_subject",
        "complainant_employee",
        "branch",
        "department",
        "site",
        "category",
    ),
    _spec("hr_cases.HRCaseEvidence", "hr_case", "provided_by_employee"),
    _spec(
        "identity.UserRoleAssignment", "role", "region", "branch", "department", "operational_zone"
    ),
    _spec(
        "incidents.Incident",
        "client",
        "contract",
        "site",
        "post",
        "branch",
        "operational_zone",
        "incident_type",
        "reporter_employee",
        "attendance_record",
        "employee_deployment",
        "site_visit",
        "inspection",
        "patrol_task",
        "patrol_run",
        "patrol_observation",
        "supervision_finding",
        "patrol_exception",
    ),
    _spec("incidents.IncidentEscalationPolicy", "incident_type", "site"),
    _spec("incidents.IncidentEvidence", "incident"),
    _spec(
        "incidents.SOSAlert",
        "employee",
        "attendance_record",
        "site",
        "post",
        "patrol_run",
        "linked_incident",
    ),
    _spec("leave.EmployeeLeavePolicyAssignment", "employee", "leave_policy"),
    _spec("leave.HolidayCalendar", "branch"),
    _spec("leave.LeaveApprovalPolicy", "leave_type", "branch", "department"),
    _spec("leave.LeaveBalanceAccount", "employee", "leave_type", "entitlement_period"),
    _spec("leave.LeaveEntitlementPeriod", "employee", "leave_type", "leave_policy"),
    _spec("leave.LeavePayrollExport", "payroll_period"),
    _spec("leave.LeaveRequest", "employee", "leave_type", "policy", "approval_policy"),
    _spec("notifications.Notification", "event", "rule"),
    _spec("organization.Branch", "region", "city"),
    _spec("organization.City", "region"),
    _spec("organization.Department", "parent", "branch"),
    _spec("organization.Designation", "department"),
    _spec("organization.OperationalZone", "branch"),
    _spec("patrol.PatrolCheckpoint", "client", "site", "post"),
    _spec("patrol.PatrolEvidence", "patrol_run", "observation"),
    _spec("patrol.PatrolException", "patrol_task", "patrol_run"),
    _spec("patrol.PatrolObservation", "patrol_run", "site", "checkpoint", "post"),
    _spec("patrol.PatrolPolicy", "branch", "site"),
    _spec(
        "patrol.PatrolRequirement",
        "branch",
        "client",
        "site",
        "patrol_route",
        "assigned_designation",
    ),
    _spec("patrol.PatrolRoute", "client", "site"),
    _spec("patrol.PatrolRun", "patrol_task", "site", "employee"),
    _spec(
        "patrol.PatrolTask",
        "branch",
        "client",
        "site",
        "patrol_requirement",
        "patrol_route",
        "assigned_employee",
        "supervisor",
    ),
    _spec("performance.EmployeePerformancePlan", "employee", "cycle", "template"),
    _spec("performance.PerformanceTemplate", "designation", "department", "branch"),
    _spec("performance.RecognitionNomination", "employee"),
    _spec("recruitment.Candidate", "referred_by_employee"),
    _spec("recruitment.CandidateApplication", "candidate", "vacancy", "hired_employee"),
    _spec("recruitment.EmploymentOffer", "application", "designation", "branch", "department"),
    _spec(
        "recruitment.ManpowerRequisition",
        "branch",
        "department",
        "designation",
        "replacement_for_employee",
    ),
    _spec(
        "recruitment.OnboardingCase",
        "application",
        "candidate",
        "accepted_offer",
        "branch",
        "department",
        "designation",
    ),
    _spec("recruitment.OnboardingChecklistTemplate", "designation"),
    _spec("recruitment.Vacancy", "manpower_requisition", "branch", "department", "designation"),
    _spec("supervision.CorrectiveAction", "finding", "site", "post", "assigned_to_employee"),
    _spec("supervision.FieldEvidence", "site_visit", "inspection", "finding", "corrective_action"),
    _spec(
        "supervision.GuardObservation",
        "site_visit",
        "site",
        "post",
        "employee",
        "attendance_record",
    ),
    _spec("supervision.InspectionFinding", "inspection", "site", "post", "employee"),
    _spec("supervision.InspectionTemplate", "site_type", "designation"),
    _spec(
        "supervision.SiteInspection", "site_visit", "site", "post", "inspected_employee", "template"
    ),
    _spec("supervision.SiteVisit", "supervisor", "visit_plan", "branch", "site"),
    _spec("supervision.SupervisionAssignment", "supervisor", "branch", "operational_zone", "site"),
    _spec("supervision.SupervisorDailyReport", "supervisor", "branch"),
    _spec(
        "supervision.SupervisorVisitPlan",
        "supervisor",
        "supervision_assignment",
        "branch",
        "site",
        "generated_from_requirement",
    ),
    _spec("supervision.VisitFrequencyRequirement", "branch", "operational_zone", "site"),
    _spec("training.EmployeeQualification", "employee", "qualification_type"),
    _spec("training.ExternalCertification", "employee", "qualification_type", "employee_document"),
    _spec("training.QualificationType", "category"),
    _spec(
        "training.TrainingCertificate",
        "employee",
        "qualification_type",
        "employee_document",
        "superseded_by",
    ),
    _spec("training.TrainingCourse", "category"),
    _spec("training.TrainingEnrollment", "session", "employee"),
    _spec("training.TrainingInstructor", "employee"),
    _spec("training.TrainingProgram", "designation"),
    _spec(
        "training.TrainingRequirement",
        "designation",
        "department",
        "branch",
        "course",
        "qualification_type",
    ),
    _spec("training.TrainingSession", "course", "program", "branch", "venue", "lead_instructor"),
    _spec("training.TrainingVenue", "branch"),
    _spec("workforce.Employee", "branch", "department", "designation"),
    _spec("workforce.EmployeeAssignmentHistory", "employee", "branch", "department", "designation"),
)


NO_INDEPENDENT_TENANT_RELATIONS = frozenset(
    {
        "analytics.AnalyticsCostAllocationPolicy",
        "analytics.AnalyticsExportJob",
        "analytics.AnalyticsPrivacyPolicy",
        "analytics.DashboardDefinition",
        "analytics.ManagementKPI",
        "assets.AssetCategory",
        "contracts.ClientIndustry",
        "contracts.PostType",
        "contracts.SiteType",
        "deployment.SchedulingPolicy",
        "documents.DocumentType",
        "finance.ApprovalPolicy",
        "finance.DocumentSequence",
        "finance.FinanceApprovalHistory",
        "finance.FinanceAttachment",
        "finance.FiscalYear",
        "finance.PaymentProviderConfiguration",
        "finance.PayrollPeriod",
        "finance.SalaryStructure",
        "hr_cases.HRCaseCategory",
        "identity.Role",
        "incidents.IncidentType",
        "leave.LeavePolicy",
        "leave.LeaveType",
        "notifications.NotificationEvent",
        "notifications.NotificationRule",
        "notifications.NotificationTemplate",
        "organization.Region",
        "performance.KPIDefinition",
        "performance.PerformanceCycle",
        "performance.PerformanceRatingScale",
        "training.TrainingCategory",
    }
)

DATABASE_CONSTRAINED_MODELS = frozenset({"organization.TenantProvisioningRequest"})
DERIVED_CHILD_FAMILIES = frozenset(
    {"billing.ClientInvoiceLine", "finance.JournalEntryLine", "finance.VendorBillLine"}
)
NON_PERSISTENT_CI_SURFACES = frozenset(
    {
        "analytics.cache_keys",
        "exports.scoped_querysets",
        "reports.scoped_querysets",
        "tasks.resource_derived_scope",
    }
)
LATER_SAAS_SURFACES = frozenset({"documents.private_file_content_integrity"})
