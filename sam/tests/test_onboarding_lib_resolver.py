"""Unit tests for the onboarding ``_lib`` resolver (Tenant-Onboarding Tooling spec, Phase 1).

Covers the two robustness primitives every onboarding runner now shares:

- ``_lib.paths`` — repo-root resolution by MARKER walk (not a fixed ``dirname`` count),
  idempotent ``sys.path`` setup, and ``import_by_path`` for modules outside a package.
- ``_lib.secrets`` — tenant secrets path resolution (``--tenant`` convention + ``--secrets``
  override), loading, and required-key reads that raise a NAMED error on a missing/blank key
  (no silent substitution — R3.1 / ONBOARDING D16).

Validates: Requirements R3 (no silent substitution), R4 (robust path/import resolution).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

# repo root on sys.path so ``scripts.sam.onboarding._lib`` imports (mirrors sibling runner
# tests' bootstrap). This is the ONE allowed path line — the thing under test IS the resolver.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ``secrets.py`` uses ``from .paths import repo_root`` (a relative import), so the package
# chain must be importable. With the repo root on sys.path, Python 3 namespace packages make
# ``scripts.onboarding._lib`` importable without any ``__init__.py`` in ``scripts/``.
paths = importlib.import_module("scripts.onboarding._lib.paths")
secrets = importlib.import_module("scripts.onboarding._lib.secrets")


# --------------------------------------------------------------------------------------------
# paths.py
# --------------------------------------------------------------------------------------------


def test_repo_root_resolves_to_the_actual_repo_root():
    """The marker walk finds the real repo root regardless of this file's depth."""
    assert paths.repo_root() == _REPO_ROOT


def test_repo_root_finds_root_from_a_deep_start(tmp_path):
    """A deep start path still walks UP to the nearest marker (not a dirname count)."""
    deep = os.path.join(
        _REPO_ROOT, "scripts", "sam", "onboarding", "_lib"
    )
    assert paths.repo_root(deep) == _REPO_ROOT


def test_repo_root_raises_clearly_when_no_marker(tmp_path):
    """Outside any repo the walk fails loudly rather than silently resolving to '/'."""
    with pytest.raises(RuntimeError, match="Could not locate the repository root"):
        paths.repo_root(str(tmp_path))


def test_ensure_backend_src_on_path_is_idempotent():
    """A second call must not grow sys.path (idempotency is 'no new duplicates').

    We assert the DELTA across a repeat call rather than an absolute count, because the test
    harness / pytest rootdir may already have the repo root on sys.path for reasons outside
    this function's control.
    """
    root = paths.ensure_backend_src_on_path()
    backend_src = os.path.join(root, "backend", "src")
    before_root = sys.path.count(root)
    before_src = sys.path.count(backend_src)
    paths.ensure_backend_src_on_path()  # second call must not add anything
    assert sys.path.count(root) == before_root
    assert sys.path.count(backend_src) == before_src
    assert root in sys.path and backend_src in sys.path


def test_import_by_path_loads_a_loose_module(tmp_path):
    mod_file = tmp_path / "loose_mod.py"
    mod_file.write_text("VALUE = 42\n", encoding="utf-8")
    mod = paths.import_by_path("loose_mod_under_test", str(mod_file))
    assert mod.VALUE == 42


def test_import_by_path_missing_file_raises_named_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="no file at"):
        paths.import_by_path("nope", str(tmp_path / "does_not_exist.py"))


# --------------------------------------------------------------------------------------------
# secrets.py
# --------------------------------------------------------------------------------------------


def test_tenant_secrets_path_uses_convention_when_no_override():
    p = secrets.tenant_secrets_path("acme")
    assert p == os.path.join(
        _REPO_ROOT, "scripts", "tenants", "acme", "secrets.local.json"
    )


def test_tenant_secrets_path_override_wins_verbatim(tmp_path):
    override = str(tmp_path / "custom.json")
    assert secrets.tenant_secrets_path("acme", override) == os.path.abspath(override)


def test_tenant_secrets_path_requires_a_tenant():
    with pytest.raises(ValueError, match="tenant is required"):
        secrets.tenant_secrets_path("")


def test_load_tenant_secrets_missing_file_names_path_and_escape_hatch():
    with pytest.raises(secrets.SecretsFileNotFoundError) as exc:
        secrets.load_tenant_secrets("tenant-with-no-file")
    msg = str(exc.value)
    assert "tenant-with-no-file" in msg
    assert "--secrets" in msg


def test_load_tenant_secrets_reads_override_file(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"sheet_id": "ABC"}), encoding="utf-8")
    data = secrets.load_tenant_secrets("acme", str(f))
    assert data == {"sheet_id": "ABC"}


def test_require_returns_present_value():
    assert secrets.require({"sheet_id": "ABC"}, "sheet_id") == "ABC"


def test_require_supports_dotted_nested_keys():
    data = {"folder_ids": {"facturen": "FID"}}
    assert secrets.require(data, "folder_ids.facturen") == "FID"


def test_require_missing_key_raises_named_error():
    with pytest.raises(secrets.MissingSecretError) as exc:
        secrets.require({}, "sheet_id")
    assert exc.value.key == "sheet_id"
    assert "sheet_id" in str(exc.value)


def test_require_blank_value_is_treated_as_missing():
    with pytest.raises(secrets.MissingSecretError):
        secrets.require({"sheet_id": "   "}, "sheet_id")


def test_require_missing_nested_key_raises_named_error():
    with pytest.raises(secrets.MissingSecretError) as exc:
        secrets.require({"folder_ids": {}}, "folder_ids.facturen")
    assert exc.value.key == "folder_ids.facturen"


# --------------------------------------------------------------------------------------------
# secrets.py — named-credentials map (R2.3 / R2.6)
# --------------------------------------------------------------------------------------------


_CREDS = {
    "credentials": {
        "google_sheets": {
            "type": "google_service_account",
            "file": "google-service-account.json",
        }
    }
}


def test_tenant_dir_resolves_under_scripts_tenants():
    assert secrets.tenant_dir("acme") == os.path.join(
        _REPO_ROOT, "scripts", "tenants", "acme"
    )


def test_tenant_dir_requires_a_tenant():
    with pytest.raises(ValueError, match="tenant is required"):
        secrets.tenant_dir("")


def test_credential_file_resolves_co_located_sibling():
    """A file-based credential resolves relative to the tenant dir (co-located, R2.3a)."""
    path = secrets.credential_file(_CREDS, "google_sheets", "h-dcn")
    assert path == os.path.join(
        _REPO_ROOT, "scripts", "tenants", "h-dcn", "google-service-account.json"
    )


def test_credential_file_override_wins_verbatim(tmp_path):
    override = str(tmp_path / "elsewhere.json")
    assert secrets.credential_file(
        _CREDS, "google_sheets", "h-dcn", override=override
    ) == os.path.abspath(override)


def test_credential_file_absolute_filename_honored_as_is(tmp_path):
    abs_name = str(tmp_path / "abs-key.json")
    creds = {"credentials": {"google_sheets": {"type": "x", "file": abs_name}}}
    assert secrets.credential_file(creds, "google_sheets", "h-dcn") == os.path.abspath(
        abs_name
    )


def test_credential_file_unknown_purpose_raises_named_error():
    with pytest.raises(secrets.MissingSecretError) as exc:
        secrets.credential_file(_CREDS, "no_such_purpose", "h-dcn")
    assert exc.value.key == "credentials.no_such_purpose.file"


def test_credential_file_entry_without_file_key_raises_named_error():
    """A non-file entry (no 'file') surfaces as a clear missing-key error (Phase 1, R2.6)."""
    creds = {"credentials": {"source_api": {"type": "api_token"}}}
    with pytest.raises(secrets.MissingSecretError) as exc:
        secrets.credential_file(creds, "source_api", "h-dcn")
    assert exc.value.key == "credentials.source_api.file"
