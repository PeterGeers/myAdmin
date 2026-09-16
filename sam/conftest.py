"""
pytest bootstrap for the module-plane shared auth tests (S2 / T8).

Puts the **repo root** on ``sys.path`` so ``import sam.shared.auth_utils`` resolves
when pytest is run from within ``sam/`` (rootdir = ``sam/``). This is intentionally
self-contained: it does **not** import or depend on anything under ``backend/src`` —
the module plane is a separate, vendorable package.
"""

import os
import sys

# sam/ -> repo root (one level up). Adding the repo root lets `sam.shared` import as a
# package without installing anything.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
