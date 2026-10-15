from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.db.models import Model

from dsms.analytics.api.views import ExecutiveViewSet
from dsms.common.integrity import get_default_registry
from dsms.common.integrity.coverage import (
    DATABASE_CONSTRAINED_MODELS,
    DERIVED_CHILD_FAMILIES,
    GLOBAL_NON_TENANT_MODELS,
    LATER_SAAS_SURFACES,
    NO_INDEPENDENT_TENANT_RELATIONS,
    NON_PERSISTENT_CI_SURFACES,
    TENANT_RELATION_SPECS,
    IntegrityCoverageClassification,
)


def _direct_company_models() -> dict[str, set[str]]:
    company = apps.get_model("organization", "Company")
    discovered: dict[str, set[str]] = {}
    for model in apps.get_models():
        if not any(
            field.name == "company" and getattr(field, "related_model", None) is company
            for field in model._meta.concrete_fields
        ):
            continue
        relations = {
            field.name
            for field in model._meta.concrete_fields
            if field.name != "company"
            and getattr(field, "related_model", None) is not None
            and getattr(field, "related_model", None) is not company
            and isinstance(field.related_model, type)
            and issubclass(field.related_model, Model)
            and any(
                related.name == "company" and getattr(related, "related_model", None) is company
                for related in field.related_model._meta.concrete_fields
            )
        }
        discovered[model._meta.label] = relations
    return discovered


def test_explicit_manifest_matches_all_direct_company_models_and_relations() -> None:
    discovered = _direct_company_models()
    scanned = {spec.model_label: set(spec.relation_fields) for spec in TENANT_RELATION_SPECS}
    assert len(scanned) == len(TENANT_RELATION_SPECS)
    classified = set(scanned) | NO_INDEPENDENT_TENANT_RELATIONS | DATABASE_CONSTRAINED_MODELS

    assert classified == set(discovered)
    assert set(scanned).isdisjoint(NO_INDEPENDENT_TENANT_RELATIONS)
    assert set(scanned).isdisjoint(DATABASE_CONSTRAINED_MODELS)
    assert all(discovered[label] == fields for label, fields in scanned.items())
    assert all(not discovered[label] for label in NO_INDEPENDENT_TENANT_RELATIONS)
    assert all(not discovered[label] for label in DATABASE_CONSTRAINED_MODELS)


def test_manifest_has_registered_checks_and_no_unknown_classification() -> None:
    registered = {check.check_id for check in get_default_registry().checks}

    assert all(spec.check_id in registered for spec in TENANT_RELATION_SPECS)
    assert all(
        spec.classification is IntegrityCoverageClassification.SCANNED
        for spec in TENANT_RELATION_SPECS
    )
    assert DERIVED_CHILD_FAMILIES
    assert {
        "subscriptions.PlanEntitlementEvent",
        "subscriptions.PlanModuleDefault",
    } == GLOBAL_NON_TENANT_MODELS
    assert NON_PERSISTENT_CI_SURFACES
    assert LATER_SAAS_SURFACES

    user_id = uuid4()
    company_a_id = uuid4()
    company_b_id = uuid4()
    request = SimpleNamespace(user=SimpleNamespace(id=user_id))
    with (
        patch(
            "dsms.analytics.api.views._company_for",
            side_effect=(
                SimpleNamespace(id=company_a_id),
                SimpleNamespace(id=company_b_id),
            ),
        ),
        patch(
            "dsms.analytics.api.views.cache.get",
            side_effect=({"tenant": "A"}, {"tenant": "B"}),
        ) as cache_get,
    ):
        assert ExecutiveViewSet()._summary(request, "CEO").data == {"tenant": "A"}
        assert ExecutiveViewSet()._summary(request, "CEO").data == {"tenant": "B"}

    keys = [call.args[0] for call in cache_get.call_args_list]
    assert keys[0] != keys[1]
    assert all(str(user_id) in key for key in keys)
    assert str(company_a_id) in keys[0]
    assert str(company_b_id) in keys[1]
