from datetime import date
from typing import Any, cast
from uuid import UUID

from django.db import models, transaction
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.identity import access
from dsms.identity.models import User

from .. import domain_selectors, domain_services
from ..enums import ApprovalDocumentType
from ..exceptions import FinanceError, to_error_dict
from ..models import Account, JournalEntry
from ..operations_models import (
    ApprovalPolicy,
    BankAccount,
    BankStatementLine,
    Budget,
    CashAccount,
    CompanyExpense,
    ExpenseCategory,
    ExpenseClaim,
    FinanceApprovalHistory,
    FinanceAttachment,
    FundTransfer,
    PettyCashFund,
    RecurringExpenseTemplate,
)
from ..payroll_models import (
    EmployeeCompensation,
    PayrollComponent,
    PayrollPeriod,
    PayrollRun,
    SalaryStructure,
)
from ..procurement_models import (
    PaymentVoucher,
    PurchaseOrder,
    PurchaseReceipt,
    PurchaseRequisition,
    Vendor,
    VendorBill,
)
from .vendor_serializers import vendor_account_error
from .views import FinancePermission

DOMAIN_MODELS: dict[str, type[models.Model]] = {
    "payroll-components": PayrollComponent,
    "salary-structures": SalaryStructure,
    "employee-compensations": EmployeeCompensation,
    "payroll-periods": PayrollPeriod,
    "payroll-runs": PayrollRun,
    "vendors": Vendor,
    "purchase-requisitions": PurchaseRequisition,
    "purchase-orders": PurchaseOrder,
    "purchase-receipts": PurchaseReceipt,
    "vendor-bills": VendorBill,
    "payment-vouchers": PaymentVoucher,
    "expense-categories": ExpenseCategory,
    "expenses": CompanyExpense,
    "expense-claims": ExpenseClaim,
    "recurring-expenses": RecurringExpenseTemplate,
    "petty-cash-funds": PettyCashFund,
    "cash-accounts": CashAccount,
    "bank-accounts": BankAccount,
    "fund-transfers": FundTransfer,
    "budgets": Budget,
    "approval-policies": ApprovalPolicy,
}

PERMISSIONS = {
    "payroll-components": "finance.manage_payroll",
    "salary-structures": "finance.manage_payroll",
    "employee-compensations": "finance.manage_payroll",
    "payroll-periods": "finance.manage_payroll",
    "payroll-runs": "finance.manage_payroll",
    "vendors": "finance.manage_procurement",
    "purchase-requisitions": "finance.manage_procurement",
    "purchase-orders": "finance.manage_procurement",
    "purchase-receipts": "finance.manage_procurement",
    "vendor-bills": "finance.manage_procurement",
    "payment-vouchers": "finance.manage_procurement",
    "expense-categories": "finance.manage_expenses",
    "expenses": "finance.manage_expenses",
    "expense-claims": "finance.manage_expenses",
    "recurring-expenses": "finance.manage_expenses",
    "petty-cash-funds": "finance.manage_expenses",
    "cash-accounts": "finance.manage_banking",
    "bank-accounts": "finance.manage_banking",
    "fund-transfers": "finance.manage_banking",
    "budgets": "finance.manage_budgets",
    "approval-policies": "finance.approve_finance",
}

SENSITIVE_FIELDS = {
    "account_number_encrypted",
    "iban_encrypted",
    "bank_details_encrypted",
}


def serializer_for(model: type[models.Model]) -> type[serializers.ModelSerializer[Any]]:
    field_names = [field.name for field in model._meta.fields if field.name not in SENSITIVE_FIELDS]
    readonly = [
        field
        for field in [
            "id",
            "created_at",
            "updated_at",
            "status",
            "payment_status",
            "approved_by",
            "journal_entry",
            "gross_total",
            "deduction_total",
            "net_total",
            "paid_amount",
            "recovered_amount",
        ]
        if field in field_names
    ]
    meta = type("Meta", (), {"model": model, "fields": field_names, "read_only_fields": readonly})
    return type(f"{model.__name__}APISerializer", (serializers.ModelSerializer,), {"Meta": meta})


def object_company(obj: models.Model) -> Any:
    if hasattr(obj, "company"):
        return obj.company
    if hasattr(obj, "employee"):
        return obj.employee.company
    raise PermissionDenied("This resource does not expose a company scope.")


class FinanceResponseSerializer(serializers.Serializer[Any]):
    """Schema marker for heterogeneous Finance workflow payloads."""


class FinanceAPIView(APIView):
    """Schema-aware base for Finance endpoints with heterogeneous payloads."""

    serializer_class = FinanceResponseSerializer


class DomainCollectionView(FinanceAPIView):
    permission_classes = [IsAuthenticated]

    def _context(self, request: Request, resource: str) -> tuple[type[models.Model], str, set[Any]]:
        model = DOMAIN_MODELS.get(resource)
        if model is None:
            raise ValidationError({"resource": ["Unknown finance resource."]})
        permission = PERMISSIONS[resource]
        self.permission_code = permission
        ids = access.get_fully_accessible_company_ids(
            cast(User, request.user), permission=permission
        )
        return model, permission, ids

    @extend_schema(operation_id="finance_domain_collection_list")
    def get(self, request: Request, resource: str) -> Response:
        model, _permission, ids = self._context(request, resource)
        manager = cast(Any, model).objects
        items = [obj for obj in manager.all() if object_company(obj).id in ids]
        return Response(serializer_for(model)(items, many=True).data)

    @transaction.atomic
    @extend_schema(operation_id="finance_domain_collection_create")
    def post(self, request: Request, resource: str) -> Response:
        model, permission, ids = self._context(request, resource)
        serializer = serializer_for(model)(data=request.data)
        serializer.is_valid(raise_exception=True)
        if model is Vendor:
            vendor_account_error(
                serializer.validated_data["company"],
                serializer.validated_data["payable_account"],
            )
        model_fields = {field.name for field in model._meta.fields}
        extras: dict[str, Any] = {}
        if "created_by" in model_fields:
            extras["created_by"] = request.user
        for field in SENSITIVE_FIELDS & model_fields:
            extras[field] = request.data.get(field, "")
        item = serializer.save(**extras)
        company = object_company(item)
        if company.id not in ids or not access.has_permission(
            user=cast(User, request.user), permission=permission, company=company
        ):
            raise PermissionDenied("Company-scoped finance permission required.")
        return Response(serializer_for(model)(item).data, status=status.HTTP_201_CREATED)


class DomainDetailView(FinanceAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="finance_domain_detail_retrieve")
    def get(self, request: Request, resource: str, pk: UUID) -> Response:
        model = DOMAIN_MODELS.get(resource)
        if model is None:
            raise ValidationError({"resource": ["Unknown finance resource."]})
        permission = PERMISSIONS[resource]
        self.permission_code = permission
        item = model.objects.get(pk=pk)  # type: ignore[attr-defined]
        if not access.has_permission(
            user=cast(User, request.user), permission=permission, company=object_company(item)
        ):
            raise PermissionDenied()
        return Response(serializer_for(model)(item).data)


class DashboardView(FinanceAPIView):
    permission_classes = [FinancePermission]
    permission_code = "finance.view_financial_dashboard"

    def get(self, request: Request, section: str = "summary") -> Response:
        company = request.query_params.get("company")
        ids = access.get_fully_accessible_company_ids(
            cast(User, request.user), permission=self.permission_code
        )
        if not company or company not in {str(item) for item in ids}:
            raise PermissionDenied()
        summary = domain_selectors.dashboard_summary(company_id=company)
        if section == "exceptions":
            return Response(domain_selectors.finance_exceptions(company_id=company))
        if section == "budget":
            return Response(summary["budget_vs_actual"])
        return Response(summary)


class ReportView(FinanceAPIView):
    permission_classes = [FinancePermission]
    permission_code = "finance.view_financial_reports"

    def get(self, request: Request, report: str) -> Response:
        company = request.query_params.get("company")
        ids = access.get_fully_accessible_company_ids(
            cast(User, request.user), permission=self.permission_code
        )
        if not company or company not in {str(item) for item in ids}:
            raise PermissionDenied()
        if report == "profit-and-loss":
            return Response(
                domain_selectors.profit_and_loss(
                    company_id=company,
                    date_from=date.fromisoformat(request.query_params["date_from"]),
                    date_to=date.fromisoformat(request.query_params["date_to"]),
                )
            )
        if report == "balance-sheet":
            return Response(
                domain_selectors.balance_sheet(
                    company_id=company, date_to=date.fromisoformat(request.query_params["date_to"])
                )
            )
        if report == "ap-aging":
            return Response(
                domain_selectors.accounts_payable_aging(
                    company_id=company,
                    as_of=date.fromisoformat(request.query_params.get("as_of", str(date.today()))),
                )
            )
        if report == "budget-vs-actual":
            return Response(domain_selectors.budget_vs_actual(company_id=company))
        if report == "general-ledger":
            return Response(list(domain_selectors.general_ledger(company_id=company).values()))
        if report == "journal-register":
            return Response(list(domain_selectors.journal_register(company_id=company).values()))
        if report == "financial-exceptions":
            return Response(domain_selectors.finance_exceptions(company_id=company))
        factory = domain_selectors.REPORT_QUERYSETS.get(report)
        if factory is None:
            raise ValidationError({"report": ["Unknown financial report."]})
        values = list(factory(company).values())  # type: ignore[no-untyped-call]
        return Response(values)


class ApprovalInboxView(FinanceAPIView):
    permission_classes = [FinancePermission]
    permission_code = "finance.approve_finance"

    def get(self, request: Request) -> Response:
        company = request.query_params.get("company")
        ids = access.get_fully_accessible_company_ids(
            cast(User, request.user), permission=self.permission_code
        )
        if not company or company not in {str(item) for item in ids}:
            raise PermissionDenied()
        submitted = FinanceApprovalHistory.objects.filter(
            company_id=company, decision="SUBMITTED"
        ).exclude(
            object_id__in=FinanceApprovalHistory.objects.filter(
                company_id=company, decision__in=["APPROVED", "REJECTED"]
            ).values("object_id")
        )
        return Response(list(submitted.values()))


class PayrollActionView(FinanceAPIView):
    permission_classes = [FinancePermission]
    permission_code = "finance.manage_payroll"

    def post(self, request: Request, pk: UUID, action: str) -> Response:
        run = PayrollRun.objects.get(pk=pk)
        if not access.has_permission(
            user=cast(User, request.user), permission=self.permission_code, company=run.company
        ):
            raise PermissionDenied()
        try:
            if action == "calculate":
                result = domain_services.calculate_payroll(payroll_run=run)
            elif action == "submit":
                result = domain_services.submit_finance_document(
                    obj=run,
                    actor=cast(User, request.user),
                    document_type=ApprovalDocumentType.PAYROLL,
                )
            elif action == "approve":
                result = domain_services.approve_finance_document(
                    obj=run,
                    actor=cast(User, request.user),
                    document_type=ApprovalDocumentType.PAYROLL,
                )
            elif action == "post":
                result = domain_services.post_payroll(
                    payroll_run=run, actor=cast(User, request.user)
                )
            elif action == "close":
                result = domain_services.close_payroll(payroll_run=run)
            else:
                raise ValidationError({"action": ["Unknown payroll action."]})
        except FinanceError as exc:
            raise ValidationError(to_error_dict(exc)) from exc
        return Response(serializer_for(PayrollRun)(result).data)


class FinanceActionView(FinanceAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="finance_domain_action_execute")
    def post(self, request: Request, resource: str, pk: UUID, action: str) -> Response:
        model = DOMAIN_MODELS.get(resource)
        if model is None:
            raise ValidationError({"resource": ["Unknown finance resource."]})
        item = cast(Any, model).objects.get(pk=pk)
        permission = PERMISSIONS[resource]
        if not access.has_permission(
            user=cast(User, request.user),
            permission=permission,
            company=object_company(item),
        ):
            raise PermissionDenied()
        document_types = {
            "purchase-requisitions": ApprovalDocumentType.PURCHASE_REQUISITION,
            "purchase-orders": ApprovalDocumentType.PURCHASE_ORDER,
            "vendor-bills": ApprovalDocumentType.VENDOR_BILL,
            "payment-vouchers": ApprovalDocumentType.PAYMENT_VOUCHER,
            "expenses": ApprovalDocumentType.EXPENSE,
            "expense-claims": ApprovalDocumentType.EXPENSE_CLAIM,
            "fund-transfers": ApprovalDocumentType.FUND_TRANSFER,
            "budgets": ApprovalDocumentType.BUDGET,
        }
        try:
            if action == "submit":
                result = domain_services.submit_finance_document(
                    obj=item,
                    actor=cast(User, request.user),
                    document_type=document_types[resource],
                )
            elif action == "approve":
                result = domain_services.approve_finance_document(
                    obj=item,
                    actor=cast(User, request.user),
                    document_type=document_types[resource],
                )
            elif action == "reject":
                result = domain_services.reject_finance_document(
                    obj=item,
                    actor=cast(User, request.user),
                    document_type=document_types[resource],
                    reason=str(request.data.get("reason", "")),
                )
            elif resource == "purchase-receipts" and action == "confirm":
                result = domain_services.confirm_receipt(receipt=item)
            elif resource == "vendor-bills" and action == "approve-and-post":
                result = domain_services.approve_and_post_vendor_bill(
                    bill=item, actor=cast(User, request.user)
                )
            elif resource == "expenses" and action == "approve-and-post":
                result = domain_services.approve_and_post_expense(
                    expense=item,
                    actor=cast(User, request.user),
                    payable_account=Account.objects.get(pk=request.data["payable_account"]),
                )
            elif resource == "expense-claims" and action == "approve-and-post":
                result = domain_services.approve_and_post_expense_claim(
                    claim=item,
                    actor=cast(User, request.user),
                    reimbursement_payable=Account.objects.get(pk=request.data["payable_account"]),
                )
            elif resource == "payment-vouchers" and action == "pay":
                result = domain_services.pay_vendor_voucher(
                    voucher=item,
                    actor=cast(User, request.user),
                    cash_account=Account.objects.get(pk=request.data["cash_account"]),
                    reference=str(request.data.get("reference", "")),
                )
            elif resource == "fund-transfers" and action == "post":
                result = domain_services.post_fund_transfer(
                    transfer=item, actor=cast(User, request.user)
                )
            else:
                raise ValidationError({"action": ["Unknown finance action."]})
        except FinanceError as exc:
            raise ValidationError(to_error_dict(exc)) from exc
        return Response(serializer_for(model)(result).data)


class BankImportView(FinanceAPIView):
    permission_classes = [FinancePermission]
    permission_code = "finance.manage_banking"

    def post(self, request: Request, pk: UUID) -> Response:
        bank = BankAccount.objects.get(pk=pk)
        if not access.has_permission(
            user=cast(User, request.user), permission=self.permission_code, company=bank.company
        ):
            raise PermissionDenied()
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["CSV file is required."]})
        try:
            statement = domain_services.import_bank_csv(
                bank_account=bank, content=upload.read(), actor=cast(User, request.user)
            )
        except FinanceError as exc:
            raise ValidationError(to_error_dict(exc)) from exc
        return Response({"id": statement.id, "line_count": statement.lines.count()}, status=201)


class BankReconcileView(FinanceAPIView):
    permission_classes = [FinancePermission]
    permission_code = "finance.manage_banking"

    def post(self, request: Request, pk: UUID, action: str) -> Response:
        line = BankStatementLine.objects.select_related("statement__bank_account").get(pk=pk)
        if not access.has_permission(
            user=cast(User, request.user),
            permission=self.permission_code,
            company=line.statement.bank_account.company,
        ):
            raise PermissionDenied()
        try:
            if action == "match":
                result = domain_services.reconcile_bank_line(
                    line=line,
                    journal=JournalEntry.objects.get(pk=request.data["journal"]),
                    actor=cast(User, request.user),
                )
            else:
                result = domain_services.classify_bank_line(
                    line=line, status=action.upper(), actor=cast(User, request.user)
                )
        except FinanceError as exc:
            raise ValidationError(to_error_dict(exc)) from exc
        return Response(
            {
                "id": result.id,
                "status": result.status,
                "matched_journal": result.matched_journal_id,
            }
        )


class FinanceAttachmentView(FinanceAPIView):
    permission_classes = [FinancePermission]
    permission_code = "finance.manage_finance_attachments"

    def post(self, request: Request) -> Response:
        from dsms.organization.models import Company

        company = Company.objects.get(pk=str(request.data.get("company")))
        if not access.has_permission(
            user=cast(User, request.user), permission=self.permission_code, company=company
        ):
            raise PermissionDenied()
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["Attachment is required."]})
        try:
            item = domain_services.create_finance_attachment(
                company=company,
                document_type=str(request.data.get("document_type")),
                object_id=request.data.get("object_id"),
                upload=upload,
                actor=cast(User, request.user),
            )
        except FinanceError as exc:
            raise ValidationError(to_error_dict(exc)) from exc
        return Response(
            {"id": item.id, "original_filename": item.original_filename, "size": item.size},
            status=201,
        )

    def get(self, request: Request, pk: UUID) -> FileResponse:
        item = FinanceAttachment.objects.get(pk=pk)
        if not access.has_permission(
            user=cast(User, request.user), permission=self.permission_code, company=item.company
        ):
            raise PermissionDenied()
        response = FileResponse(item.file.open("rb"), content_type=item.content_type)
        response["Content-Disposition"] = f'attachment; filename="{item.original_filename}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
