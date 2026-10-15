"""
Cross-plane import-boundary guard for the SAM / Lambda plane
(spec full-test-suite-fixes-2026-10-15, task L2 — durable prevention for the C1 class).

WHY THIS EXISTS
---------------
The SAM / DynamoDB plane is deliberately MySQL-free: its handlers persist to DynamoDB
(boto3), not MySQL, and its CI job installs only ``sam/shared/requirements.txt`` +
boto3 — never ``mysql-connector-python``. The Flask/MySQL plane is a SEPARATE plane whose
``backend/src/database.py`` does a module-level ``import mysql.connector``.

C1 (2026-10-15) was the textbook cross-plane leak: ``test_member_data_invariance_props.py``
imported a Flask/MySQL-plane migration DRIVER
(``migrate_overrides_to_fixed_overrides``) only to reach one PURE, DB-free transform
(``rename_overrides_key``) — but that driver's top-level ``from database import
DatabaseManager`` dragged in ``mysql.connector``, which the SAM env does not install. The
SAM job went red at COLLECTION with ``ModuleNotFoundError: No module named 'mysql'`` — and
ONLY in CI, because a local dev venv HAS mysql-connector-python installed and silently masks
the leak.

The durable guard is a ``sys.meta_path`` finder installed in ``sam/tests/conftest.py`` that
blocks ``mysql`` / ``mysql.connector`` for the whole SAM session, so a re-introduced leak dies
fast EVERYWHERE (not just CI) with a clear cross-plane message. This test proves that guard:
  1. it does NOT break the legitimate C1 import surface (the pure transform + a boto3-backed
     SAM handler import), and
  2. it DOES fire the instant a SAM import transitively pulls in ``mysql.connector`` — the
     exact C1 chain (``from database import DatabaseManager`` → ``import mysql.connector``).

Each case runs in a CHILD PROCESS that reproduces the guard independently of what happens to
be installed locally, mirroring the sibling Flask-free guard (``test_import_boundary_no_flask``).
"""

import os
import subprocess
import sys
import textwrap

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The child-process prelude installs the SAME mysql block the conftest installs, drops any
# warm ``mysql`` module, and wires the SAM plane's sys.path (repo root + backend/src +
# backend/src/migrations) so the imports under test resolve exactly as they do under pytest.
_PRELUDE = textwrap.dedent(
    """
    import os
    import sys

    class _BlockMysql:
        def find_spec(self, name, path, target=None):
            if name == "mysql" or name.startswith("mysql."):
                raise ModuleNotFoundError(
                    "SAM plane must not import mysql.connector (cross-plane leak)"
                )
            return None

    sys.meta_path.insert(0, _BlockMysql())
    for _m in [m for m in list(sys.modules) if m == "mysql" or m.startswith("mysql.")]:
        del sys.modules[_m]
    """
)


def _run_import_with_mysql_blocked(import_stmt: str) -> subprocess.CompletedProcess:
    """Run ``import_stmt`` in a child process where importing ``mysql[.connector]`` is blocked."""
    backend_src = os.path.join(_REPO_ROOT, "backend", "src")
    migrations = os.path.join(backend_src, "migrations")

    code = _PRELUDE + "\n" + import_stmt + "\n"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [_REPO_ROOT, backend_src, migrations, env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_block_mysql_finder_actually_blocks_mysql():
    """Sanity check: the child-process mysql block really does make ``mysql.connector`` unimportable.

    Guards against the test passing vacuously — if the blocking mechanism broke, ``import
    mysql.connector`` would succeed only because mysql-connector-python happens to be installed
    locally (it is, in the backend .venv this suite runs under), hiding a real leak.
    """
    result = _run_import_with_mysql_blocked("import mysql.connector")
    assert result.returncode != 0, (
        "Expected 'import mysql.connector' to FAIL under the mysql block, but it succeeded — "
        "the guard's blocking mechanism is not working.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "cross-plane leak" in result.stderr


def test_c1_pure_transform_import_still_works_without_mysql():
    """The legitimate C1 import surface must import cleanly with ``mysql`` blocked (no false positive).

    The invariance test only needs the PURE, DB-free transform ``rename_overrides_key``. Imported
    from the ``overrides_key_transform`` module (NOT the DB-bound migration driver), it carries no
    MySQL dependency — so it must import fine even with the mysql block active. A boto3-backed SAM
    handler import is included to confirm the guard leaves normal SAM/DynamoDB imports untouched.
    """
    for import_stmt in (
        "from overrides_key_transform import rename_overrides_key",
        "import sam.members.handler",
    ):
        result = _run_import_with_mysql_blocked(import_stmt)
        assert result.returncode == 0, (
            f"'{import_stmt}' must import on the SAM plane with mysql blocked, but it failed "
            f"(false positive — the guard is blocking a legitimate import):\n{result.stderr}"
        )
        assert "cross-plane leak" not in result.stderr


def test_reintroduced_c1_leak_fires_the_guard():
    """A re-introduced C1-style leak must FIRE the guard at import time.

    This reproduces the exact C1 chain WITHOUT committing a bad import: importing the DB-bound
    migration driver (``migrate_overrides_to_fixed_overrides``) transitively does
    ``from database import DatabaseManager`` → ``import mysql.connector``. With the guard active
    that import must fail fast with the cross-plane-leak message, pinpointing the leak — rather
    than passing locally (where mysql-connector-python is installed) and only reddening nightly CI.
    """
    result = _run_import_with_mysql_blocked(
        "import migrate_overrides_to_fixed_overrides"
    )
    assert result.returncode != 0, (
        "Expected importing the DB-bound migration driver to FIRE the mysql guard (it "
        "transitively imports mysql.connector), but it succeeded — the guard did not catch "
        f"the re-introduced C1 leak.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "cross-plane leak" in result.stderr, (
        "The failure did not carry the guard's cross-plane-leak message — the import may have "
        f"failed for an unrelated reason:\n{result.stderr}"
    )
