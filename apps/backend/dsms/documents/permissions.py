from typing import Any, cast

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from dsms.identity import access
from dsms.identity.models import User

from .models import DocumentType, EmployeeDocument


class HasDocumentPermission(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        user = cast(User, request.user)
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.is_superuser:
            return True
        permission = getattr(view, "required_permission", None)
        if permission is None:
            action = getattr(view, "action", "")
            permission = getattr(view, "action_permissions", {}).get(action)
        return bool(permission and permission in access.get_effective_permissions(user))

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user = cast(User, request.user)
        if user.is_superuser:
            return True
        if isinstance(obj, DocumentType):
            if obj.company_id is None:
                return False
            return access.has_permission(
                user=user,
                permission=getattr(view, "required_permission", "documents.manage_document_types"),
                company=obj.company,
            )
        document = cast(EmployeeDocument, obj)
        permission = getattr(view, "action_permissions", {}).get(
            getattr(view, "action", ""), "documents.view_employeedocument"
        )
        employee = document.employee
        return access.has_permission(
            user=user,
            permission=permission,
            company=employee.company,
            region=employee.branch.region if employee.branch else None,
            branch=employee.branch,
            department=employee.department,
        )
