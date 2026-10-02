"""tenant_resolver.py — tenant-wide onboarding-secrets resolution for runners (R2/R3).

A tenant's cross-module, cross-plane ONBOARDING material lives in ONE tenant-owned place:

    scripts/tenants/<tenant>/secrets.local.json      (git-ignored, real IDs + credentials map)
    scripts/tenants/<tenant>/secrets.example.json    (committed, non-secret template)
    scripts/tenants/<tenant>/<credential>.json       (git-ignored, CO-LOCATED credential file)

Credentials are a NAMED MAP keyed by purpose (R2.3); each file-based entry names a credential
file that lives beside the secrets file in the SAME tenant dir (R2.3a) — ownership is obvious
from the path. These are ONBOARDING-ONLY credentials, not the production secret store (R2.2).

    "credentials": { "google_sheets": { "type": "google_service_account",
                                         "file": "google-service-account.json" } }

Precedence (design §3.3):
    explicit per-value CLI flag  >  secrets.local.json (via --secrets or convention path)
                                 >  (error — never a silent default)

No silent substitution (R3.1, mirrors ONBOARDING Decision D16): :func:`require` /
:func:`credential_file` raise a clear, NAMED error when something required is missing or blank —
they never return a placeholder.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from .paths import repo_root

#: Conventional filename for a tenant's real (git-ignored) secrets.
SECRETS_LOCAL_FILENAME = "secrets.local.json"


class SecretsFileNotFoundError(FileNotFoundError):
    """Raised when the resolved tenant secrets file does not exist."""


class MissingSecretError(KeyError):
    """Raised when a required key is absent or blank in the loaded secrets."""

    def __init__(self, key: str, source: str) -> None:
        self.key = key
        self.source = source
        super().__init__(
            f"required secret {key!r} is missing or blank in {source!r}. "
            "Add it to the tenant's secrets.local.json (see secrets.example.json), "
            "or pass the corresponding CLI flag."
        )


def tenant_secrets_path(tenant: str, override: str | None = None) -> str:
    """Resolve the secrets file path for ``tenant``.

    ``override`` (the ``--secrets`` flag) wins verbatim; otherwise the convention path
    ``<repo>/scripts/tenants/<tenant>/secrets.local.json`` (R3.3). ``--tenant`` itself has no
    default and is the caller's responsibility (R3.2).
    """
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if not tenant:
        raise ValueError("tenant is required to resolve the secrets path (no default).")
    return os.path.join(
        repo_root(), "scripts", "tenants", tenant, SECRETS_LOCAL_FILENAME
    )


def load_tenant_secrets(tenant: str, override: str | None = None) -> dict[str, Any]:
    """Load + parse the tenant secrets JSON.

    Raises :class:`SecretsFileNotFoundError` (naming the resolved path and the ``--secrets``
    escape hatch) if the file is absent, so a run never proceeds with blank values.
    """
    path = tenant_secrets_path(tenant, override)
    if not os.path.isfile(path):
        raise SecretsFileNotFoundError(
            f"tenant secrets file not found at {path!r}. Copy secrets.example.json to "
            "secrets.local.json and fill in real values, or pass --secrets <path>."
        )
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path!r} must contain a JSON object at the top level.")
    return data


def require(secrets: Mapping[str, Any], key: str, *, source: str = "secrets.local.json") -> Any:
    """Return ``secrets[key]`` or raise :class:`MissingSecretError` naming the key.

    "Blank" means ``None`` or an empty/whitespace string. Supports dotted keys for nested
    lookups (e.g. ``folder_ids.facturen``).
    """
    value: Any = secrets
    for part in key.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise MissingSecretError(key, source)
        value = value[part]
    if value is None or (isinstance(value, str) and not value.strip()):
        raise MissingSecretError(key, source)
    return value


def tenant_dir(tenant: str) -> str:
    """Return the tenant-owned onboarding dir ``<repo>/scripts/tenants/<tenant>``."""
    if not tenant:
        raise ValueError("tenant is required to resolve the tenant dir (no default).")
    return os.path.join(repo_root(), "scripts", "tenants", tenant)


def credential_file(
    secrets: Mapping[str, Any],
    purpose: str,
    tenant: str,
    *,
    override: str | None = None,
    base_dir: str | None = None,
    source: str = "secrets.local.json",
) -> str:
    """Resolve the absolute path to a named credential's CO-LOCATED file (R2.3/R2.6).

    Looks up ``credentials.<purpose>.file`` in the loaded ``secrets`` and resolves it RELATIVE
    to the tenant dir, so e.g. ``credentials.google_sheets.file == "google-service-account.json"``
    → ``<repo>/scripts/tenants/<tenant>/google-service-account.json`` (git-ignored).

    Precedence (R3.3): an explicit ``override`` (the ``--credentials`` flag) wins verbatim.
    ``base_dir`` lets a caller resolve a RELATIVE filename against a different directory than the
    convention tenant dir — e.g. when ``--secrets`` points at a secrets file elsewhere, the key
    is expected beside THAT file. An absolute ``file`` value is always honored as-is.

    A missing purpose/entry/file key, or a blank value, raises :class:`MissingSecretError`
    naming the dotted key (R3.1) — never a silent default.

    Phase 1 resolves only FILE-BASED credentials (R2.6). The entry's ``type`` is carried in the
    config as a declarative hint but is not branched on here until another kind is wired; a
    non-file entry (no ``file`` key) therefore surfaces as a clear missing-key error.
    """
    if override:
        return os.path.abspath(os.path.expanduser(override))

    filename = require(secrets, f"credentials.{purpose}.file", source=source)
    if not isinstance(filename, str):
        raise MissingSecretError(f"credentials.{purpose}.file", source)

    expanded = os.path.expanduser(filename)
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    return os.path.join(base_dir if base_dir else tenant_dir(tenant), expanded)
