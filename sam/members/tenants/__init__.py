"""
S5 — tenant-scoped packages for the generic Members module (design C5, Property 5).

The generic membership core (``sam/members/domain/*``) is tenant-**agnostic**: it never
contains an ``if tenant == "…"``. Everything genuinely bespoke to a single tenant that cannot
be expressed as config (Rung 1) or a declarative rule (Rung 2) lives here, under a
per-tenant sub-package, and is wired into the generic core ONLY through the named extension
points of :class:`sam.members.domain.tenant_hooks.TenantHookRegistry` (Rung 3).

So a tenant literal (e.g. ``tenant_id="h-dcn"``) and a tenant's business logic appear only
inside its own sub-package (``sam/members/tenants/hdcn/``) plus that package's tests — never
in the engine. Adding a tenant is additive: drop in a sub-package and register its hooks.
"""
