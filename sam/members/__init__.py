"""
Generic Members module (S5) — one SAM-backed deployable, four layers.

Layout (dependencies point downward only; nothing skips a layer — see
``.kiro/steering/35-sam-module-architecture-sam.md``)::

    handler/       thin HTTP edge (parse · verified auth · entitlement · route · respond)
    domain/        storage-agnostic, tenant-agnostic business rules (this is app logic)
    repository/    the ONLY DynamoDB touch-point; tenant scoping (tenant_id PK + LeadingKeys)

h-dcn is the first tenant of this generic module (config + overlay + data + hooks),
never a conditional in the generic core.
"""
