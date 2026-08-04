# Backend structure

The backend is a modular Django monolith. `common` holds reusable foundations; `identity`, `organization`, and `audit` own their respective domain concerns.

Rules:

- Views orchestrate HTTP only.
- Serializers validate transport data.
- Services execute business commands and transactions.
- Selectors perform complex queries.
- Models enforce data integrity and entity-level behavior.
- Celery tasks call services.
- Signals must not contain core business logic.
