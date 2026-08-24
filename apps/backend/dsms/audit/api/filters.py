import django_filters

from ..models import AuditEvent


class AuditEventFilter(django_filters.FilterSet):  # type: ignore[misc]
    date_from = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    date_to = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")
    actor = django_filters.UUIDFilter(field_name="actor_user_id")
    source_object = django_filters.CharFilter(field_name="source_object_id")

    class Meta:
        model = AuditEvent
        fields = [
            "date_from",
            "date_to",
            "actor",
            "category",
            "action",
            "company",
            "branch",
            "source_app",
            "source_object",
            "success",
            "severity",
        ]
