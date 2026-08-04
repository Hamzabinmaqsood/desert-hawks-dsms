# ADR 0001: Modular monolith

## Decision

DSMS begins as one Django deployment with explicitly bounded domain applications.

## Rationale

The platform needs coherent transactional behavior, a small operational footprint, and rapid early delivery. Microservices would introduce distributed consistency, deployment, observability, and coordination costs before independent scaling needs are proven.

## Boundary rules

Each domain owns its models, services, selectors, serializers, views, and tasks. Cross-domain access uses intentional public interfaces rather than reaching into internals. Dependency direction and APIs are reviewed as domains grow.

## Future extraction

A service may be extracted only when it has stable boundaries, independently scalable workload or reliability needs, a clear data-ownership migration path, and the team capacity to operate it.
