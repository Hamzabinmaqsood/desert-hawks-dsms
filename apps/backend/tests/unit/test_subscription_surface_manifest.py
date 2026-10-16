from __future__ import annotations

from importlib import import_module
from typing import Any

from django.urls import URLPattern, URLResolver, get_resolver

from dsms.subscriptions.modules import TENANT_MODULE_REGISTRY
from dsms.subscriptions.surfaces import (
    TASK_SURFACE_MANIFEST,
    exempt_route_kind,
)


def _patterns(resolver: URLResolver) -> list[URLPattern]:
    found: list[URLPattern] = []
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            found.extend(_patterns(pattern))
        else:
            found.append(pattern)
    return found


def test_every_repository_api_route_is_gated_core_or_internal_platform() -> None:
    unclassified: list[str] = []
    for pattern in _patterns(get_resolver()):
        callback = pattern.callback
        view_class = getattr(callback, "cls", None)
        if view_class is None:
            continue
        module = view_class.__module__
        if module.startswith(("django.", "rest_framework.", "drf_spectacular.")):
            continue
        if module == "config.views":
            continue
        required = getattr(view_class, "required_module_ids", ())
        if required:
            for module_id in required:
                TENANT_MODULE_REGISTRY.get(module_id)
            continue
        if exempt_route_kind(view_class) is not None:
            continue
        unclassified.append(f"{pattern.pattern}: {module}.{view_class.__name__}")

    assert unclassified == []


def test_all_registered_project_tasks_have_explicit_surface_classification() -> None:
    assert len(TASK_SURFACE_MANIFEST) == 12
    for dotted_path, classification in TASK_SURFACE_MANIFEST.items():
        module_name, attribute = dotted_path.rsplit(".", maxsplit=1)
        task: Any = getattr(import_module(module_name), attribute)
        assert task.name == dotted_path
        if classification not in {"CORE", "ORIGIN_DERIVED"}:
            TENANT_MODULE_REGISTRY.get(classification)
