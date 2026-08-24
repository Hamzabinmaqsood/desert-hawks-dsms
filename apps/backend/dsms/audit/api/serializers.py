from rest_framework import serializers

from dsms.identity import access

from ..models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    class Meta:
        model = AuditEvent
        fields = "__all__"
        read_only_fields = tuple(field.name for field in AuditEvent._meta.fields)

    def to_representation(self, instance: AuditEvent) -> dict[str, object]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not request or not access.has_permission(
            user=request.user,
            permission="audit.view_sensitive_audit_metadata",
            company=instance.company,
            region=instance.region,
            branch=instance.branch,
        ):
            data["metadata_safe"] = {}
            data["ip_address"] = None
            data["user_agent_summary"] = ""
        return data
