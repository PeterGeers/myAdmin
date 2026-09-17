"""
S4 D2 — the Pool A Pre-Token-Generation Lambda (the projection mechanism).

This package is the **identity-account** serverless code that stamps a user's
resolved per-tenant entitlement into the Pool A token at issuance. It lives under
``sam/`` because it is packaged and deployed like the module plane's serverless
code — it is NOT part of the Flask request path.

Unlike the module-plane verifier in ``sam/shared/`` (which is deliberately
self-contained and never imports ``backend/src``), this Lambda **imports the
shared resolution logic** from ``backend/src/auth/`` — the T1 resolver
(:func:`auth.entitlement_resolver.resolve_entitlement`) and the T4 codec
(:mod:`auth.entitlement_claim_codec`) plus ``MODULE_REGISTRY``. That is the whole
point of S4's "one rule, two carriers": the Lambda and the Flask plane compute the
*identical* answer because they call the *same* pure function. Copying the rule
into ``sam/`` would let the two carriers drift, which S4 forbids.

Packaging (documented for T18 deploy)
-------------------------------------
The deployment bundle for this Lambda vendors these backend modules onto the
Python path (e.g. via a build step that copies ``backend/src/auth/*`` and
``backend/src/services/module_registry.py`` into the artifact, or ships them as a
Lambda layer). The handler adds ``backend/src`` to ``sys.path`` at import time so
``import auth.entitlement_resolver`` / ``import services.module_registry`` resolve
in every environment (local test, CI, and the deployed Lambda).
"""
