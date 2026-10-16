from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import wraps
from inspect import signature
from typing import Any, TypeVar, cast

from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import PermissionDenied

from dsms.organization.models import Company

from .entitlements import EffectiveModuleResult, resolve_effective_modules
from .modules import TENANT_MODULE_REGISTRY

FunctionT = TypeVar("FunctionT", bound=Callable[..., Any])

_OWNER_ATTRIBUTES = (
    "company",
    "employee",
    "address",
    "contact",
    "client",
    "contract",
    "site",
    "post",
    "branch",
    "store",
    "handoff",
    "issue",
    "return_record",
    "invoice",
    "receipt",
    "vendor",
    "vendor_bill",
    "bill",
    "voucher",
    "payroll_run",
    "item",
    "variable",
    "advance",
    "expense",
    "claim",
    "transfer",
    "fund",
    "bank_account",
    "line",
    "budget",
    "batch",
    "profile",
    "instruction",
    "settlement",
    "roster_period",
    "roster",
    "duty_shift",
    "schedule_block",
    "replacement_request",
    "attendance_record",
    "attendance_period",
    "correction_request",
    "correction",
    "period",
    "conflict",
    "leave_request",
    "application",
    "vacancy",
    "requisition",
    "offer",
    "onboarding",
    "background_check",
    "course",
    "session",
    "enrollment",
    "requirement",
    "waiver",
    "qualification",
    "station",
    "patrol_task",
    "patrol_run",
    "site_visit",
    "visit",
    "inspection",
    "finding",
    "exception",
    "observation",
    "corrective_action",
    "action",
    "hr_case",
    "appeal",
    "investigation",
    "plan",
    "performance_plan",
    "assignment",
    "snapshot",
    "original",
    "subscription",
)


class ModuleNotEnabled(PermissionDenied):
    """Stable, tenant-safe denial used by HTTP and supported service entry points."""

    status_code = 403
    default_code = "module_not_enabled"
    default_detail = "The required product module is not enabled for this Company."

    def __init__(self, required_module_ids: Iterable[str]) -> None:
        required = TENANT_MODULE_REGISTRY.ordered_ids(required_module_ids)
        super().__init__(
            {
                "detail": self.default_detail,
                "required_modules": list(required),
            },
            code=self.default_code,
        )
        self.required_module_ids = required


def company_from_resource(value: Any, *, _seen: set[int] | None = None) -> Company | None:
    if value is None:
        return None
    if isinstance(value, Company):
        return value
    seen = _seen or set()
    marker = id(value)
    if marker in seen:
        return None
    seen.add(marker)
    for attribute in _OWNER_ATTRIBUTES:
        try:
            related = getattr(value, attribute)
        except (AttributeError, ObjectDoesNotExist):
            continue
        company = company_from_resource(related, _seen=seen)
        if company is not None:
            return company
    return None


def _request_cache(
    request: Any,
) -> tuple[
    dict[tuple[Any, str, int], EffectiveModuleResult],
    dict[Any, tuple[Any, str, int]],
]:
    cache = getattr(request, "_tenant_module_entitlement_cache", None)
    latest = getattr(request, "_tenant_module_entitlement_latest", None)
    if cache is None or latest is None:
        cache = {}
        latest = {}
        request._tenant_module_entitlement_cache = cache
        request._tenant_module_entitlement_latest = latest
    return cache, latest


def resolve_company_modules(
    company: Company, *, request: Any | None = None
) -> EffectiveModuleResult:
    """Resolve once per Company/revision in a request without global caching."""

    if request is not None:
        cache, latest = _request_cache(request)
        key = latest.get(company.pk)
        if key is not None and key in cache:
            return cache[key]
    result = resolve_effective_modules(company)
    if request is not None:
        cache, latest = _request_cache(request)
        key = (company.pk, result.policy_mode, result.entitlement_revision)
        cache[key] = result
        latest[company.pk] = key
    return result


def company_has_module(company: Company, module_id: str, *, request: Any | None = None) -> bool:
    normalized = TENANT_MODULE_REGISTRY.get(module_id).module_id
    return normalized in resolve_company_modules(company, request=request).module_ids


def company_ids_with_module(
    module_id: str, *, company_ids: Iterable[Any] | None = None
) -> tuple[Any, ...]:
    """Return active Companies entitled to a module for scheduled batch work."""

    normalized = TENANT_MODULE_REGISTRY.get(module_id).module_id
    queryset = Company.objects.filter(is_active=True)
    if company_ids is not None:
        queryset = queryset.filter(pk__in=tuple(company_ids))
    return tuple(company.pk for company in queryset if company_has_module(company, normalized))


def require_company_module(
    company: Company, module_id: str, *, request: Any | None = None
) -> EffectiveModuleResult:
    return require_company_modules(company, (module_id,), request=request)


def require_company_modules(
    company: Company,
    module_ids: Iterable[str],
    *,
    request: Any | None = None,
) -> EffectiveModuleResult:
    required = TENANT_MODULE_REGISTRY.ordered_ids(module_ids)
    result = resolve_company_modules(company, request=request)
    missing = tuple(module_id for module_id in required if module_id not in result.module_ids)
    if missing:
        raise ModuleNotEnabled(missing)
    return result


def requires_company_module(module_id: str, *, argument: str) -> Callable[[FunctionT], FunctionT]:
    """Guard a supported service entry point using its authoritative resource argument."""

    TENANT_MODULE_REGISTRY.get(module_id)

    def decorate(function: FunctionT) -> FunctionT:
        call_signature = signature(function)
        if argument not in call_signature.parameters:
            raise ValueError(
                f"Unknown Company authority argument {argument!r} for "
                f"{function.__module__}.{function.__name__}"
            )

        @wraps(function)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            bound = call_signature.bind(*args, **kwargs)
            company = company_from_resource(bound.arguments.get(argument))
            if company is None:
                raise RuntimeError(
                    f"Cannot derive Company for {function.__module__}.{function.__name__}"
                )
            require_company_module(company, module_id)
            return function(*args, **kwargs)

        return cast(FunctionT, guarded)

    return decorate
