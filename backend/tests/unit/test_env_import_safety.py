"""Regression test for the `load_dotenv clobbers AWS_PROFILE` bugfix.

Background (see
`.kiro/specs/BUGS/20261012 load_dotenv clobbers AWS_PROFILE/analysis.md`):
eight backend modules used to call `load_dotenv(backend/.env)` at *import* time. The
committed `.env` files export static personal-account AWS keys, so merely importing one
of those modules re-injected `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` into the
process env. boto3 ranks static env keys ABOVE `AWS_PROFILE`, so this silently clobbered
an operator's attempt to target `nonprofit-deploy` and sent calls to the wrong account.

Task 1 of the bugfix removed those import-time side-effects. This test locks that in:
importing a backend module must NOT mutate pre-set `AWS_*` env.

Validates: analysis.md acceptance #1 ("Importing any backend module does NOT mutate
pre-set AWS_* env").

Why this would FAIL against pre-fix code: the pre-fix modules called
`load_dotenv(backend/.env)` at import, which re-injects `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` from the committed env file. After the import the two keys would
be *set* (not unset), tripping the assertions below.
"""
import importlib
import os
import sys

import pytest

# The eight de-dotenv'd modules; we exercise `database` plus one other per the task.
# Imported by bare name because conftest puts `backend/src` on sys.path.
_MODULES_UNDER_TEST = ("database", "transaction_logic")

_STATIC_KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")


@pytest.fixture
def clean_aws_env(monkeypatch):
    """Set AWS_PROFILE and guarantee the two static keys are unset.

    monkeypatch restores the full pre-test os.environ on teardown, so this test does not
    pollute AWS_* for any other test regardless of how the import mutated the env.
    """
    monkeypatch.setenv("AWS_PROFILE", "nonprofit-deploy")
    for key in _STATIC_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


def _fresh_import(module_name):
    """Import `module_name` with no cached copy, so any import-time side-effect runs.

    Drop the module (and reset finder caches) before importing so a module already
    imported by an earlier test cannot mask a would-be import-time load_dotenv.
    """
    sys.modules.pop(module_name, None)
    importlib.invalidate_caches()
    return importlib.import_module(module_name)


@pytest.mark.unit
@pytest.mark.parametrize("module_name", _MODULES_UNDER_TEST)
def test_importing_backend_module_does_not_reinject_static_aws_keys(
    clean_aws_env, module_name
):
    """Importing a backend module must not set the static AWS keys from the .env file."""
    for key in _STATIC_KEYS:
        assert key not in os.environ, f"precondition: {key} must be unset before import"

    _fresh_import(module_name)

    for key in _STATIC_KEYS:
        assert key not in os.environ, (
            f"Importing '{module_name}' re-injected {key} into os.environ. "
            "An import-time load_dotenv() of a key-bearing .env has crept back in; "
            "this is the AWS_PROFILE-clobber bug (analysis.md F2)."
        )


@pytest.mark.unit
@pytest.mark.parametrize("module_name", _MODULES_UNDER_TEST)
def test_importing_backend_module_leaves_aws_profile_unchanged(
    clean_aws_env, module_name
):
    """Importing a backend module must leave a pre-set AWS_PROFILE untouched."""
    assert os.environ.get("AWS_PROFILE") == "nonprofit-deploy"

    _fresh_import(module_name)

    assert os.environ.get("AWS_PROFILE") == "nonprofit-deploy", (
        f"Importing '{module_name}' changed AWS_PROFILE out from under the operator."
    )
