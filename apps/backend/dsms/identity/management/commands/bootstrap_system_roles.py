"""Idempotently create the platform's baseline system role templates.

Safe to re-run: existing roles are updated in place (name/description/
permission set), never duplicated. Intended for the first few foundational
modules only -- final business role matrices (HR Manager, Guard, etc.) will
be introduced as those modules land.
"""

from typing import Any

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from dsms.identity.models import Role

_ORGANIZATION_MODELS = [
    "company",
    "region",
    "city",
    "branch",
    "department",
    "designation",
    "operationalzone",
]
_WORKFORCE_CHILD_MODELS = ["employeeaddress", "emergencycontact"]


def _crud_perms(app_label: str, models: list[str], verbs: tuple[str, ...]) -> list[tuple[str, str]]:
    return [(app_label, f"{verb}_{model}") for model in models for verb in verbs]


_SYSTEM_ROLES: list[dict[str, Any]] = [
    {
        "code": "ORGANIZATION_ADMIN",
        "name": "Organization Administrator",
        "description": "Full read/write access to organization master data.",
        "permissions": _crud_perms("organization", _ORGANIZATION_MODELS, ("view", "add", "change")),
    },
    {
        "code": "ORGANIZATION_VIEWER",
        "name": "Organization Viewer",
        "description": "Read-only access to organization master data.",
        "permissions": _crud_perms("organization", _ORGANIZATION_MODELS, ("view",)),
    },
    {
        "code": "ACCESS_ADMIN",
        "name": "Access Administrator",
        "description": (
            "Manages users, roles, and role assignments; can view organization "
            "master data for scope selection."
        ),
        "permissions": (
            _crud_perms("identity", ["user"], ("view", "add", "change"))
            + [
                ("identity", "manage_roles"),
                ("identity", "view_access_matrix"),
                ("identity", "assign_roles"),
            ]
            + _crud_perms("organization", _ORGANIZATION_MODELS, ("view",))
        ),
    },
    {
        "code": "WORKFORCE_ADMIN",
        "name": "Workforce Administrator",
        "description": "Manages employee master data within assigned organizational scopes.",
        "permissions": (
            _crud_perms("workforce", ["employee"], ("view", "add", "change"))
            + _crud_perms("workforce", _WORKFORCE_CHILD_MODELS, ("view", "add", "change"))
            + [
                ("workforce", "view_sensitive_employee_data"),
                ("workforce", "manage_employee_status"),
                ("workforce", "manage_employee_assignment"),
                ("workforce", "link_employee_user"),
            ]
            + _crud_perms("organization", _ORGANIZATION_MODELS, ("view",))
        ),
    },
    {
        "code": "WORKFORCE_VIEWER",
        "name": "Workforce Viewer",
        "description": "Reads basic employee master data within assigned scopes.",
        "permissions": _crud_perms("workforce", ["employee"], ("view",)),
    },
    {
        "code": "DOCUMENT_ADMIN",
        "name": "Document Administrator",
        "description": "Manages employee document metadata and private files within scope.",
        "permissions": (
            _crud_perms("documents", ["documenttype"], ("view", "add", "change"))
            + _crud_perms("documents", ["employeedocument"], ("view", "add", "change"))
            + _crud_perms("documents", ["employeedocumentversion"], ("view", "add"))
            + [
                ("documents", "manage_document_types"),
                ("documents", "view_sensitive_document_data"),
                ("documents", "download_employee_document"),
                ("documents", "view_document_audit"),
            ]
            + _crud_perms("organization", _ORGANIZATION_MODELS, ("view",))
        ),
    },
    {
        "code": "DOCUMENT_VERIFIER",
        "name": "Document Verifier",
        "description": "Reviews, verifies, rejects, and revokes employee documents within scope.",
        "permissions": _crud_perms(
            "documents", ["employeedocument", "employeedocumentversion"], ("view",)
        )
        + [
            ("documents", "view_sensitive_document_data"),
            ("documents", "download_employee_document"),
            ("documents", "verify_employee_document"),
            ("documents", "revoke_employee_document"),
            ("documents", "view_document_audit"),
        ],
    },
    {
        "code": "DOCUMENT_VIEWER",
        "name": "Document Viewer",
        "description": "Reads non-sensitive employee document metadata within scope.",
        "permissions": _crud_perms("documents", ["employeedocument"], ("view",)),
    },
    {
        "code": "FINANCE_ADMIN",
        "name": "Finance Administrator",
        "description": "Finance configuration and accounting operations within scope.",
        "permissions": _crud_perms(
            "finance",
            [
                "account",
                "fiscalyear",
                "accountingperiod",
                "costcenter",
                "journalentry",
                "journalline",
                "paymentproviderconfiguration",
                "paymentbeneficiaryprofile",
                "paymentdestinationchange",
                "paymentaccountingprofile",
                "paymentbatch",
                "paymentinstruction",
                "paymentinstructionallocation",
                "paymentprovidertransaction",
                "paymentprovidersettlement",
                "paymentprovidersettlementline",
            ],
            ("view", "add", "change"),
        )
        + [
            ("finance", "manage_chart_of_accounts"),
            ("finance", "manage_fiscal_periods"),
            ("finance", "create_journal"),
            ("finance", "approve_journal"),
            ("finance", "post_journal"),
            ("finance", "reverse_journal"),
            ("finance", "view_financial_reports"),
            ("finance", "view_financial_dashboard"),
            ("finance", "view_finance_audit"),
            ("finance", "manage_payroll"),
            ("finance", "manage_procurement"),
            ("finance", "manage_expenses"),
            ("finance", "manage_banking"),
            ("finance", "manage_budgets"),
            ("finance", "approve_finance"),
            ("finance", "view_sensitive_finance_data"),
            ("finance", "manage_finance_attachments"),
            ("finance", "manage_payment_providers"),
            ("finance", "view_sensitive_payment_destination"),
            ("finance", "approve_payment_destination"),
            ("finance", "prepare_payment_batch"),
            ("finance", "import_payment_settlement"),
            ("finance", "reconcile_payment_settlement"),
        ],
    },
    {
        "code": "PAYMENT_PREPARER",
        "name": "Payment Preparer",
        "description": "Prepares payment destinations and disbursement batches.",
        "permissions": [
            ("finance", "prepare_payment_batch"),
            ("finance", "view_paymentbeneficiaryprofile"),
            ("finance", "view_paymentbatch"),
            ("finance", "view_paymentinstruction"),
        ],
    },
    {
        "code": "PAYMENT_APPROVER",
        "name": "Payment Approver",
        "description": "Approves payment destinations and payment batches independently.",
        "permissions": [
            ("finance", "approve_payment_destination"),
            ("finance", "approve_payment_batch"),
            ("finance", "view_paymentbeneficiaryprofile"),
            ("finance", "view_paymentbatch"),
        ],
    },
    {
        "code": "PAYMENT_RELEASER",
        "name": "Payment Releaser",
        "description": "Releases approved batches and controls safe retries.",
        "permissions": [
            ("finance", "release_payment_batch"),
            ("finance", "retry_payment"),
            ("finance", "view_paymentbatch"),
            ("finance", "view_paymentinstruction"),
        ],
    },
    {
        "code": "PAYMENT_RECONCILER",
        "name": "Payment Reconciler",
        "description": "Imports and reconciles provider settlement records.",
        "permissions": [
            ("finance", "import_payment_settlement"),
            ("finance", "reconcile_payment_settlement"),
            ("finance", "view_paymentinstruction"),
            ("finance", "view_paymentprovidersettlement"),
        ],
    },
    {
        "code": "PAYROLL_ADMIN",
        "name": "Payroll Administrator",
        "description": "Manages compensation, payroll calculation, posting, and payment.",
        "permissions": [
            ("finance", "manage_payroll"),
            ("finance", "view_sensitive_finance_data"),
            ("finance", "view_financial_reports"),
            ("finance", "view_financial_dashboard"),
        ],
    },
    {
        "code": "ACCOUNTANT",
        "name": "Accountant",
        "description": "Journal and ledger operations within scope.",
        "permissions": [
            ("finance", "create_journal"),
            ("finance", "post_journal"),
            ("finance", "view_financial_reports"),
            ("finance", "manage_expenses"),
            ("finance", "manage_banking"),
        ],
    },
    {
        "code": "FINANCE_APPROVER",
        "name": "Finance Approver",
        "description": "Independent financial approval within scope.",
        "permissions": [
            ("finance", "approve_journal"),
            ("finance", "approve_finance"),
            ("finance", "view_financial_dashboard"),
        ],
    },
    {
        "code": "PROCUREMENT_OFFICER",
        "name": "Procurement Officer",
        "description": "Manages requisitions, purchase orders, receipts, and vendor bills.",
        "permissions": [
            ("finance", "manage_procurement"),
            ("finance", "manage_finance_attachments"),
            ("finance", "view_financial_dashboard"),
        ],
    },
    {
        "code": "FINANCE_AUDITOR",
        "name": "Finance Auditor",
        "description": "Read-only financial records and audit access.",
        "permissions": _crud_perms(
            "finance",
            [
                "account",
                "fiscalyear",
                "accountingperiod",
                "costcenter",
                "journalentry",
                "journalline",
            ],
            ("view",),
        )
        + [
            ("finance", "view_financial_reports"),
            ("finance", "view_finance_audit"),
        ],
    },
    {
        "code": "FINANCE_EXECUTIVE_VIEWER",
        "name": "Finance Executive Viewer",
        "description": "High-level reports without sensitive banking data.",
        "permissions": [
            ("finance", "view_financial_reports"),
            ("finance", "view_financial_dashboard"),
        ],
    },
    {
        "code": "RECRUITMENT_ADMIN",
        "name": "Recruitment Administrator",
        "description": "Full recruitment and onboarding administration within assigned scope.",
        "permissions": _crud_perms(
            "recruitment",
            [
                "manpowerrequisition",
                "vacancy",
                "candidate",
                "candidateapplication",
                "candidatescreening",
                "interview",
                "candidateassessment",
                "candidatereference",
                "backgroundcheck",
                "candidatedocument",
                "employmentoffer",
                "onboardingcase",
                "onboardingchecklisttemplate",
                "onboardingchecklistitem",
            ],
            ("view", "add", "change"),
        )
        + [
            ("recruitment", "approve_requisition"),
            ("recruitment", "approve_offer"),
            ("recruitment", "hire_candidate"),
            ("recruitment", "download_candidate_document"),
            ("recruitment", "view_candidate_sensitive_data"),
            ("recruitment", "view_offer_salary"),
            ("recruitment", "waive_background_check"),
        ],
    },
    {
        "code": "RECRUITER",
        "name": "Recruiter",
        "description": "Manages candidates and recruitment workflows.",
        "permissions": _crud_perms(
            "recruitment",
            [
                "vacancy",
                "candidate",
                "candidateapplication",
                "candidatescreening",
                "interview",
                "candidateassessment",
                "candidatereference",
                "candidatedocument",
            ],
            ("view", "add", "change"),
        ),
    },
    {
        "code": "RECRUITMENT_APPROVER",
        "name": "Recruitment Approver",
        "description": "Approves recruitment requisitions and offers.",
        "permissions": [
            ("recruitment", "view_manpowerrequisition"),
            ("recruitment", "approve_requisition"),
            ("recruitment", "view_employmentoffer"),
            ("recruitment", "approve_offer"),
        ],
    },
    {
        "code": "INTERVIEWER",
        "name": "Interviewer",
        "description": "Views assigned interviews and records evaluations.",
        "permissions": _crud_perms(
            "recruitment", ["interview", "interviewevaluation"], ("view", "add")
        ),
    },
    {
        "code": "BACKGROUND_VERIFIER",
        "name": "Background Verifier",
        "description": "Records background and reference verification outcomes.",
        "permissions": _crud_perms(
            "recruitment", ["backgroundcheck", "referenceverification"], ("view", "add", "change")
        ),
    },
    {
        "code": "ONBOARDING_ADMIN",
        "name": "Onboarding Administrator",
        "description": "Manages accepted-candidate onboarding and hiring.",
        "permissions": _crud_perms(
            "recruitment",
            ["onboardingcase", "onboardingchecklisttemplate", "onboardingchecklistitem"],
            ("view", "add", "change"),
        )
        + [("recruitment", "hire_candidate")],
    },
    {
        "code": "RECRUITMENT_VIEWER",
        "name": "Recruitment Viewer",
        "description": "Read-only non-sensitive recruitment access.",
        "permissions": _crud_perms(
            "recruitment",
            [
                "manpowerrequisition",
                "vacancy",
                "candidate",
                "candidateapplication",
                "interview",
                "candidateassessment",
                "employmentoffer",
                "onboardingcase",
            ],
            ("view",),
        ),
    },
    {
        "code": "TRAINING_ADMIN",
        "name": "Training Administrator",
        "description": "Full training, certification, qualification, and readiness administration.",
        "permissions": _crud_perms(
            "training",
            [
                "trainingcategory",
                "trainingcourse",
                "trainingcourseversion",
                "qualificationtype",
                "employeequalification",
                "trainingrequirement",
                "trainingrequirementwaiver",
                "trainingvenue",
                "traininginstructor",
                "trainingprogram",
                "trainingsession",
                "trainingenrollment",
                "trainingsessionparticipation",
                "trainingassessment",
                "employeetrainingassessmentresult",
                "trainingcompletion",
                "trainingcertificate",
                "externalcertification",
            ],
            ("view", "add", "change"),
        )
        + [
            ("training", "manage_course_versions"),
            ("training", "manage_requirement_waivers"),
            ("training", "finalize_training_result"),
            ("training", "issue_certificate"),
            ("training", "revoke_certificate"),
            ("training", "view_training_dashboard"),
            ("training", "view_readiness"),
            ("training", "view_training_reports"),
            ("training", "view_training_audit"),
        ],
    },
    {
        "code": "TRAINING_COORDINATOR",
        "name": "Training Coordinator",
        "description": "Coordinates courses, sessions, enrollments, and attendance within scope.",
        "permissions": _crud_perms(
            "training",
            [
                "trainingcourse",
                "trainingvenue",
                "traininginstructor",
                "trainingprogram",
                "trainingsession",
                "trainingenrollment",
                "trainingsessionparticipation",
            ],
            ("view", "add", "change"),
        ),
    },
    {
        "code": "TRAINER",
        "name": "Trainer",
        "description": "Records assigned-session attendance and assessment results.",
        "permissions": _crud_perms("training", ["trainingsession", "trainingenrollment"], ("view",))
        + _crud_perms(
            "training",
            ["trainingsessionparticipation", "employeetrainingassessmentresult"],
            ("view", "add", "change"),
        ),
    },
    {
        "code": "TRAINING_VERIFIER",
        "name": "Training Verifier",
        "description": "Finalizes results and verifies qualifications and certifications.",
        "permissions": _crud_perms(
            "training",
            [
                "trainingcompletion",
                "trainingcertificate",
                "employeequalification",
                "externalcertification",
            ],
            ("view", "add", "change"),
        )
        + [
            ("training", "finalize_training_result"),
            ("training", "issue_certificate"),
            ("training", "revoke_certificate"),
        ],
    },
    {
        "code": "TRAINING_VIEWER",
        "name": "Training Viewer",
        "description": "Read-only training records within scope.",
        "permissions": _crud_perms(
            "training",
            [
                "trainingcourse",
                "trainingsession",
                "trainingenrollment",
                "trainingcompletion",
                "trainingcertificate",
            ],
            ("view",),
        )
        + [("training", "view_training_dashboard"), ("training", "view_training_reports")],
    },
    {
        "code": "READINESS_VIEWER",
        "name": "Readiness Viewer",
        "description": "Views calculated workforce readiness without document or salary access.",
        "permissions": [("training", "view_readiness"), ("training", "view_training_dashboard")],
    },
    {
        "code": "CONTRACT_ADMIN",
        "name": "Contract Administrator",
        "description": "Full contract and site configuration.",
        "permissions": _crud_perms(
            "contracts",
            [
                "client",
                "clientcontact",
                "servicecontract",
                "contractcommercialterms",
                "securitysite",
                "securitypost",
                "staffingrequirement",
            ],
            ("view", "add", "change"),
        )
        + [
            ("contracts", "approve_contract"),
            ("contracts", "activate_contract"),
            ("contracts", "terminate_contract"),
            ("contracts", "renew_contract"),
            ("contracts", "view_commercial_terms"),
            ("contracts", "manage_commercial_terms"),
        ],
    },
    {
        "code": "CLIENT_RELATIONSHIP_MANAGER",
        "name": "Client Relationship Manager",
        "description": "Manages clients and contacts.",
        "permissions": _crud_perms(
            "contracts", ["client", "clientcontact", "servicecontract"], ("view", "add", "change")
        ),
    },
    {
        "code": "CONTRACT_APPROVER",
        "name": "Contract Approver",
        "description": "Approves and activates contracts.",
        "permissions": [
            ("contracts", "view_servicecontract"),
            ("contracts", "approve_contract"),
            ("contracts", "activate_contract"),
        ],
    },
    {
        "code": "OPERATIONS_CONTRACT_VIEWER",
        "name": "Operations Contract Viewer",
        "description": "Views operational requirements without pricing.",
        "permissions": _crud_perms(
            "contracts", ["securitysite", "securitypost", "staffingrequirement"], ("view",)
        ),
    },
    {
        "code": "SITE_CONFIGURATION_ADMIN",
        "name": "Site Configuration Administrator",
        "description": "Configures sites, posts, and requirements.",
        "permissions": _crud_perms(
            "contracts",
            [
                "securitysite",
                "siteoperationalprofile",
                "securitypost",
                "postqualificationrequirement",
                "postcredentialrequirement",
                "staffingrequirement",
            ],
            ("view", "add", "change"),
        )
        + [("contracts", "manage_site_operational_profile")],
    },
    {
        "code": "COMMERCIAL_VIEWER",
        "name": "Commercial Viewer",
        "description": "Views commercial terms without staffing mutation.",
        "permissions": [
            ("contracts", "view_servicecontract"),
            ("contracts", "view_contractcommercialterms"),
            ("contracts", "view_commercial_terms"),
        ],
    },
    {
        "code": "CONTRACT_AUDITOR",
        "name": "Contract Auditor",
        "description": "Read-only contract lifecycle records.",
        "permissions": _crud_perms(
            "contracts",
            [
                "client",
                "servicecontract",
                "contractamendment",
                "securitysite",
                "securitypost",
                "staffingrequirement",
            ],
            ("view",),
        ),
    },
    {
        "code": "DEPLOYMENT_ADMIN",
        "name": "Deployment Administrator",
        "description": "Full deployment and roster administration.",
        "permissions": _crud_perms(
            "deployment",
            [
                "employeedeployment",
                "deploymentpool",
                "deploymentpoolmembership",
                "shifttemplate",
                "schedulingpolicy",
                "rosterperiod",
                "dutyshift",
                "dutyassignment",
                "employeescheduleblock",
                "replacementrequest",
            ],
            ("view", "add", "change"),
        )
        + [
            ("deployment", "activate_deployment"),
            ("deployment", "end_deployment"),
            ("deployment", "generate_roster"),
            ("deployment", "approve_roster"),
            ("deployment", "publish_roster"),
            ("deployment", "lock_roster"),
            ("deployment", "assign_employee"),
            ("deployment", "replace_employee"),
            ("deployment", "emergency_assignment"),
            ("deployment", "allow_overstaffing"),
        ],
    },
    {
        "code": "ROSTER_PLANNER",
        "name": "Roster Planner",
        "description": "Generates and edits draft rosters without final approval.",
        "permissions": _crud_perms(
            "deployment", ["rosterperiod", "dutyshift", "dutyassignment"], ("view", "add", "change")
        )
        + [("deployment", "generate_roster"), ("deployment", "assign_employee")],
    },
    {
        "code": "ROSTER_APPROVER",
        "name": "Roster Approver",
        "description": "Approves and publishes validated rosters.",
        "permissions": [
            ("deployment", "view_rosterperiod"),
            ("deployment", "approve_roster"),
            ("deployment", "publish_roster"),
        ],
    },
    {
        "code": "OPERATIONS_MANAGER",
        "name": "Operations Manager",
        "description": "Manages operational deployment and controlled roster changes.",
        "permissions": _crud_perms(
            "deployment",
            [
                "employeedeployment",
                "rosterperiod",
                "dutyshift",
                "dutyassignment",
                "replacementrequest",
            ],
            ("view", "add", "change"),
        )
        + [
            ("deployment", "activate_deployment"),
            ("deployment", "assign_employee"),
            ("deployment", "replace_employee"),
        ],
    },
    {
        "code": "BRANCH_OPERATIONS_VIEWER",
        "name": "Branch Operations Viewer",
        "description": "Read-only planned deployment and roster information within scope.",
        "permissions": _crud_perms(
            "deployment",
            ["employeedeployment", "rosterperiod", "dutyshift", "dutyassignment"],
            ("view",),
        ),
    },
    {
        "code": "RELIEF_COORDINATOR",
        "name": "Relief Coordinator",
        "description": "Coordinates relief pools and replacement requests.",
        "permissions": _crud_perms(
            "deployment",
            ["deploymentpool", "deploymentpoolmembership", "replacementrequest"],
            ("view", "add", "change"),
        )
        + [("deployment", "replace_employee")],
    },
    {
        "code": "DEPLOYMENT_AUDITOR",
        "name": "Deployment Auditor",
        "description": "Read-only deployment, roster, and change history.",
        "permissions": _crud_perms(
            "deployment",
            [
                "employeedeployment",
                "rosterperiod",
                "dutyshift",
                "dutyassignment",
                "rosterchangeevent",
            ],
            ("view",),
        ),
    },
    {
        "code": "ATTENDANCE_ADMIN",
        "name": "Attendance Administrator",
        "description": "Full attendance policy, evidence, review, and period administration.",
        "permissions": _crud_perms(
            "attendance",
            [
                "attendancepolicy",
                "attendanceqrstation",
                "attendanceperiod",
                "attendancerecord",
                "attendanceevent",
                "attendanceverification",
                "attendanceexception",
                "attendancecorrectionrequest",
            ],
            ("view", "add", "change"),
        )
        + [
            ("attendance", "view_sensitive_location_data"),
            ("attendance", "view_biometric_verification_details"),
        ],
    },
    {
        "code": "ATTENDANCE_REVIEWER",
        "name": "Attendance Reviewer",
        "description": "Reviews records, corrections, and exceptions.",
        "permissions": _crud_perms(
            "attendance",
            ["attendancerecord", "attendanceexception", "attendancecorrectionrequest"],
            ("view", "change"),
        ),
    },
    {
        "code": "ATTENDANCE_APPROVER",
        "name": "Attendance Approver",
        "description": "Approves reviewed attendance and periods.",
        "permissions": _crud_perms(
            "attendance",
            ["attendancerecord", "attendanceperiod", "attendancecorrectionrequest"],
            ("view", "change"),
        ),
    },
    {
        "code": "SITE_ATTENDANCE_SUPERVISOR",
        "name": "Site Attendance Supervisor",
        "description": "Views and verifies site attendance within assigned scope.",
        "permissions": _crud_perms(
            "attendance", ["attendancerecord", "attendanceexception"], ("view", "change")
        ),
    },
    {
        "code": "BRANCH_ATTENDANCE_VIEWER",
        "name": "Branch Attendance Viewer",
        "description": "Read-only branch attendance summaries.",
        "permissions": _crud_perms(
            "attendance", ["attendancerecord", "attendanceexception"], ("view",)
        ),
    },
    {
        "code": "ATTENDANCE_AUDITOR",
        "name": "Attendance Auditor",
        "description": "Read-only attendance evidence and audit history.",
        "permissions": _crud_perms(
            "attendance",
            [
                "attendancerecord",
                "attendanceevent",
                "attendanceverification",
                "attendanceexception",
                "attendancechangeevent",
            ],
            ("view",),
        )
        + [
            ("attendance", "view_sensitive_location_data"),
            ("attendance", "view_biometric_verification_details"),
        ],
    },
    {
        "code": "GUARD_ATTENDANCE_SELF_SERVICE",
        "name": "Guard Attendance Self Service",
        "description": "Own duty check-in, checkout, and attendance history only.",
        "permissions": [
            ("attendance", "view_own_attendance"),
            ("attendance", "perform_own_checkin"),
            ("attendance", "perform_own_checkout"),
        ],
    },
    {
        "code": "SUPERVISION_ADMIN",
        "name": "Supervision Administrator",
        "description": "Administers field supervision records and configuration.",
        "permissions": _crud_perms(
            "supervision",
            [
                "supervisionassignment",
                "supervisorvisitplan",
                "sitevisit",
                "inspectiontemplate",
                "siteinspection",
                "inspectionfinding",
                "correctiveaction",
                "supervisordailyreport",
            ],
            ("view", "add", "change"),
        )
        + [
            ("supervision", "view_guard_observation"),
            ("supervision", "view_sensitive_field_evidence"),
        ],
    },
    {
        "code": "FIELD_SUPERVISOR",
        "name": "Field Supervisor",
        "description": (
            "Performs assigned visits, inspections, guard verification, and daily reports."
        ),
        "permissions": [
            ("supervision", code)
            for code in (
                "start_site_visit",
                "end_site_visit",
                "perform_site_inspection",
                "perform_post_inspection",
                "perform_guard_inspection",
                "verify_guard",
                "submit_daily_report",
            )
        ],
    },
    {
        "code": "SUPERVISION_PLANNER",
        "name": "Supervision Planner",
        "description": "Plans and schedules supervisor visits.",
        "permissions": [("supervision", "create_visitplan"), ("supervision", "approve_visitplan")],
    },
    {
        "code": "SUPERVISION_REVIEWER",
        "name": "Supervision Reviewer",
        "description": "Reviews site inspections and daily reports.",
        "permissions": [
            ("supervision", "review_inspection"),
            ("supervision", "review_daily_report"),
        ],
    },
    {
        "code": "OPERATIONS_SUPERVISION_MANAGER",
        "name": "Operations Supervision Manager",
        "description": "Monitors and approves branch supervision activity.",
        "permissions": [
            ("supervision", "view_supervision_dashboard"),
            ("supervision", "approve_daily_report"),
            ("supervision", "manage_finding"),
        ],
    },
    {
        "code": "CORRECTIVE_ACTION_MANAGER",
        "name": "Corrective Action Manager",
        "description": "Assigns and verifies corrective actions.",
        "permissions": [
            ("supervision", "create_corrective_action"),
            ("supervision", "assign_corrective_action"),
            ("supervision", "verify_corrective_action"),
        ],
    },
    {
        "code": "SUPERVISION_AUDITOR",
        "name": "Supervision Auditor",
        "description": "Read-only supervision reports and audit evidence.",
        "permissions": [
            ("supervision", "view_supervision_reports"),
            ("supervision", "view_supervision_audit"),
            ("supervision", "view_guard_observation"),
            ("supervision", "view_sensitive_field_evidence"),
            ("supervision", "download_field_evidence"),
        ],
    },
    {
        "code": "PATROL_ADMIN",
        "name": "Patrol Administrator",
        "description": "Administers patrol configuration and operational records.",
        "permissions": _crud_perms(
            "patrol",
            [
                "patrolpolicy",
                "patrolcheckpoint",
                "patrolroute",
                "patrolrouteversion",
                "patrolrequirement",
                "patroltask",
                "patrolrun",
                "patrolexception",
            ],
            ("view", "add", "change"),
        ),
    },
    {
        "code": "PATROL_PLANNER",
        "name": "Patrol Planner",
        "description": "Plans routes, requirements, tasks, and assignments.",
        "permissions": [
            ("patrol", "manage_patrolroute"),
            ("patrol", "manage_route_versions"),
            ("patrol", "manage_patrol_requirements"),
            ("patrol", "assign_patroltask"),
        ],
    },
    {
        "code": "PATROL_OPERATOR",
        "name": "Patrol Operator",
        "description": "Monitors current patrol execution and exceptions.",
        "permissions": [
            ("patrol", "view_patrol_dashboard"),
            ("patrol", "view_patrolrun"),
            ("patrol", "view_patrol_exceptions"),
        ],
    },
    {
        "code": "PATROL_SUPERVISOR",
        "name": "Patrol Supervisor",
        "description": "Supervises checkpoint verification within operational responsibility.",
        "permissions": [("patrol", "review_patrolrun"), ("patrol", "view_patrol_exceptions")],
    },
    {
        "code": "PATROL_REVIEWER",
        "name": "Patrol Reviewer",
        "description": "Reviews patrol runs and resolves operational exceptions.",
        "permissions": [("patrol", "review_patrolrun"), ("patrol", "resolve_patrol_exception")],
    },
    {
        "code": "PATROL_AUDITOR",
        "name": "Patrol Auditor",
        "description": "Reads patrol reports, audit history, location, and evidence.",
        "permissions": [
            ("patrol", "view_patrol_reports"),
            ("patrol", "view_patrol_audit"),
            ("patrol", "view_sensitive_patrol_location"),
            ("patrol", "download_patrol_evidence"),
        ],
    },
    {
        "code": "GUARD_PATROL_SELF_SERVICE",
        "name": "Guard Patrol Self Service",
        "description": "Performs only the guard's own assigned patrols.",
        "permissions": [("patrol", "perform_own_patrol")],
    },
    {
        "code": "BILLING_ADMIN",
        "name": "Billing Administrator",
        "description": "Manages implemented billing profiles, invoices, receipts, and allocations.",
        "permissions": _crud_perms(
            "billing",
            [
                "clientbillingprofile",
                "billingschedule",
                "billingrule",
                "taxcode",
                "clientinvoice",
                "clientinvoiceline",
                "clientreceipt",
                "clientreceiptallocation",
                "clientcreditnote",
                "clientcreditnoteline",
                "clientdebitnote",
                "clientdebitnoteline",
                "clientreceiptreversal",
                "clientcollectionactivity",
                "clientinvoicedocument",
            ],
            ("view", "add", "change"),
        )
        + [
            ("billing", code)
            for code in ("approve_invoice", "issue_invoice", "void_invoice", "download_invoice")
        ],
    },
    {
        "code": "BILLING_APPROVER",
        "name": "Billing Approver",
        "description": "Approves and issues invoices under maker/checker controls.",
        "permissions": [
            ("billing", "view_clientinvoice"),
            ("billing", "approve_invoice"),
            ("billing", "issue_invoice"),
        ],
    },
    {
        "code": "NOTIFICATION_ADMIN",
        "name": "Notification Administrator",
        "description": "Manages notification rules and safe delivery testing.",
        "permissions": [
            ("notifications", code)
            for code in (
                "manage_notification_rules",
                "view_notification_dashboard",
                "monitor_notification_delivery",
                "send_test_notification",
            )
        ],
    },
    {
        "code": "NOTIFICATION_MONITOR",
        "name": "Notification Monitor",
        "description": "Monitors notification delivery without changing rules.",
        "permissions": [
            ("notifications", "view_notification_dashboard"),
            ("notifications", "monitor_notification_delivery"),
        ],
    },
    {
        "code": "LEAVE_ADMIN",
        "name": "Leave Administrator",
        "description": "Administers leave policy, balances, requests, and reporting.",
        "permissions": [
            ("leave", code)
            for code in (
                "view_leave_dashboard",
                "manage_leavetype",
                "manage_leavepolicy",
                "manage_policy_assignments",
                "view_leave_balance",
                "adjust_leave_balance",
                "manage_leave_entitlements",
                "approve_leave_request",
                "reject_leave_request",
                "approve_leave_cancellation",
                "extend_leave",
                "recall_employee_from_leave",
                "view_sensitive_leave_details",
                "download_leave_attachment",
                "manage_holiday_calendar",
                "view_team_availability",
                "view_operations_availability",
                "export_leave_to_payroll",
                "view_leave_reports",
            )
        ],
    },
    {
        "code": "LEAVE_SELF_SERVICE",
        "name": "Leave Self Service",
        "description": "Creates and views only the linked employee's leave requests.",
        "permissions": [
            ("leave", code)
            for code in (
                "create_own_leave_request",
                "view_own_leave_request",
                "change_own_draft_leave_request",
                "request_leave_cancellation",
            )
        ],
    },
    {
        "code": "ASSET_ADMIN",
        "name": "Asset Administrator",
        "description": "Administers inventory and implemented custody workflows.",
        "permissions": _crud_perms(
            "assets",
            [
                "assetcategory",
                "assetitem",
                "assetstore",
                "asset",
                "assetissue",
                "assetissueline",
                "assetreturn",
                "stockaccount",
            ],
            ("view", "add", "change"),
        )
        + [
            ("assets", code)
            for code in (
                "view_controlled_asset",
                "view_asset_financial_values",
                "approve_asset_issue",
                "issue_asset",
                "adjust_stock",
            )
        ],
    },
    {
        "code": "ASSET_CUSTODIAN",
        "name": "Asset Custodian",
        "description": "Issues and receives assets without financial-value access.",
        "permissions": [
            ("assets", code)
            for code in (
                "view_asset",
                "view_assetissue",
                "change_assetissue",
                "approve_asset_issue",
                "issue_asset",
            )
        ],
    },
    {
        "code": "HR_CASE_MANAGER",
        "name": "HR Case Manager",
        "description": "Manages confidential HR case investigation and decisions.",
        "permissions": [
            ("hr_cases", code)
            for code in (
                "view_hrcase",
                "triage_hrcase",
                "investigate_hrcase",
                "view_confidential_case",
                "view_highly_confidential_case",
                "decide_hrcase",
            )
        ],
    },
    {
        "code": "HR_CASE_VIEWER",
        "name": "HR Case Viewer",
        "description": "Reads permitted non-highly-confidential HR cases.",
        "permissions": [("hr_cases", "view_hrcase"), ("hr_cases", "view_confidential_case")],
    },
    {
        "code": "PERFORMANCE_ADMIN",
        "name": "Performance Administrator",
        "description": "Administers performance plans, finalization, calibration, and recognition.",
        "permissions": [
            ("performance", code)
            for code in (
                "view_employeeperformanceplan",
                "change_employeeperformanceplan",
                "finalize_performance_review",
                "view_performance_score",
                "view_calibration_details",
                "approve_recognition",
            )
        ],
    },
    {
        "code": "PERFORMANCE_REVIEWER",
        "name": "Performance Reviewer",
        "description": "Reviews assigned performance plans and scores.",
        "permissions": [
            ("performance", "view_employeeperformanceplan"),
            ("performance", "view_performance_score"),
        ],
    },
    {
        "code": "ANALYTICS_ADMIN",
        "name": "Analytics Administrator",
        "description": "Manages analytics definitions, snapshots, quality, and exports.",
        "permissions": [
            ("analytics", code)
            for code in (
                "view_analyticsmetricdefinition",
                "view_executive_dashboard",
                "view_data_quality",
                "manage_analytics",
                "export_analytics",
            )
        ],
    },
    {
        "code": "EXECUTIVE_ANALYTICS_VIEWER",
        "name": "Executive Analytics Viewer",
        "description": "Views aggregate executive dashboards without raw sensitive records.",
        "permissions": [
            ("analytics", "view_analyticsmetricdefinition"),
            ("analytics", "view_executive_dashboard"),
        ],
    },
    {
        "code": "INCIDENT_MANAGER",
        "name": "Incident Manager",
        "description": "Manages the implemented incident response lifecycle.",
        "permissions": [
            ("incidents", code)
            for code in (
                "view_incident",
                "view_incident_dashboard",
                "report_incident",
                "manage_incident",
                "acknowledge_incident",
                "triage_incident",
                "assign_incident_owner",
                "manage_incident_response",
                "contain_incident",
                "resolve_incident",
                "close_incident",
                "reopen_incident",
                "manage_responders",
                "manage_incident_actions",
                "escalate_incident",
                "upload_incident_evidence",
                "download_incident_evidence",
                "view_sensitive_incident_location",
                "view_sensitive_incident_participants",
                "manage_post_incident_review",
                "view_incident_reports",
            )
        ],
    },
    {
        "code": "INCIDENT_AUDITOR",
        "name": "Incident Auditor",
        "description": "Reads incident reports and audit evidence.",
        "permissions": [
            ("incidents", code)
            for code in (
                "view_incident",
                "view_incident_reports",
                "view_incident_audit",
                "download_incident_evidence",
            )
        ],
    },
    {
        "code": "GUARD_SOS_SELF_SERVICE",
        "name": "Guard SOS Self Service",
        "description": "Triggers and views only the linked employee's SOS events.",
        "permissions": [("incidents", "trigger_own_sos"), ("incidents", "view_own_sos")],
    },
    {
        "code": "CLIENT_PORTAL_ADMIN",
        "name": "Client Portal Administrator",
        "description": "Administers external portal memberships and portal audit access.",
        "permissions": [
            ("client_portal", "view_clientportalmembership"),
            ("client_portal", "change_clientportalmembership"),
            ("client_portal", "manage_client_users"),
            ("client_portal", "view_portal_audit"),
        ],
    },
    {
        "code": "AUDIT_ADMIN",
        "name": "Audit Administrator",
        "description": "Administers audit access and may view safe and sensitive event metadata.",
        "permissions": _crud_perms("audit", ["auditevent"], ("view",))
        + [
            ("audit", "view_sensitive_audit_metadata"),
            ("audit", "export_audit"),
            ("audit", "view_audit_dashboard"),
        ],
    },
    {
        "code": "AUDIT_VIEWER",
        "name": "Audit Viewer",
        "description": "Reads privacy-minimized audit events within assigned scopes.",
        "permissions": [("audit", "view_auditevent")],
    },
    {
        "code": "SECURITY_AUDITOR",
        "name": "Security Auditor",
        "description": "Reviews security audit events and dashboards within assigned scopes.",
        "permissions": [
            ("audit", "view_auditevent"),
            ("audit", "view_sensitive_audit_metadata"),
            ("audit", "view_audit_dashboard"),
        ],
    },
]


class Command(BaseCommand):
    help = "Idempotently create/update the platform's baseline system roles."

    def handle(self, *args: Any, **options: Any) -> None:
        with transaction.atomic():
            for spec in _SYSTEM_ROLES:
                role, _created = Role.objects.update_or_create(
                    company=None,
                    code=spec["code"],
                    defaults={
                        "name": spec["name"],
                        "description": spec["description"],
                        "is_system": True,
                        "is_active": True,
                    },
                )
                permission_objects = []
                missing: list[str] = []
                for app_label, codename in spec["permissions"]:
                    try:
                        permission_objects.append(
                            Permission.objects.get(
                                content_type__app_label=app_label, codename=codename
                            )
                        )
                    except Permission.DoesNotExist:
                        missing.append(f"{app_label}.{codename}")
                if missing:
                    self.stderr.write(
                        self.style.WARNING(
                            f"{spec['code']}: skipping missing permissions: {', '.join(missing)}"
                        )
                    )
                role.permissions.set(permission_objects)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Bootstrapped {spec['code']} ({len(permission_objects)} permissions)"
                    )
                )
