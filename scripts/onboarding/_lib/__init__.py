"""Shared helpers for tenant-onboarding tooling (Tenant-Onboarding Tooling spec, Phase 1).

This package carries the two robustness primitives the onboarding runners share so no runner
has to hand-roll fragile path logic:

- :mod:`_lib.paths` — put the repo root + ``backend/src`` on ``sys.path`` by walking up to a
  repo MARKER (not by counting ``os.path.dirname`` levels), plus an ``import_by_path`` helper
  for loading a module that lives outside any importable package (e.g. a dashed tenant dir).
- :mod:`_lib.tenant_resolver` — resolve a tenant's ``scripts/tenants/<tenant>/secrets.local.json``
  (overridable with ``--secrets``), load it, and read required keys with a clear, named error
  when a key is absent or blank (no silent substitution — ONBOARDING Decision D16).

Design contract: see
``.kiro/specs/Common/Tenant/tenant-onboarding-tooling/design.md`` §3.
"""

from __future__ import annotations

from .paths import ensure_backend_src_on_path, import_by_path, repo_root
from .tenant_resolver import (
    MissingSecretError,
    SecretsFileNotFoundError,
    credential_file,
    load_tenant_secrets,
    require,
    tenant_dir,
    tenant_secrets_path,
)

__all__ = [
    "repo_root",
    "ensure_backend_src_on_path",
    "import_by_path",
    "tenant_secrets_path",
    "tenant_dir",
    "load_tenant_secrets",
    "require",
    "credential_file",
    "MissingSecretError",
    "SecretsFileNotFoundError",
]
