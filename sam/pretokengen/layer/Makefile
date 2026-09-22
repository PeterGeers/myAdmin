# Makefile builder for the PreTokenGen Lambda layer (S5c task 5.2, C-PTG).
#
# `sam build` invokes the `build-PreTokenGenLayer` target with $(ARTIFACTS_DIR)
# set to the layer's staging dir. A Python Lambda layer exposes its packages
# under `python/` on `sys.path`, so this target assembles exactly the things the
# handler imports at runtime — and nothing else — under `$(ARTIFACTS_DIR)/python`:
#
#   python/sam/__init__.py        the `sam` namespace package so `import
#                                 sam.pretokengen.*` resolves as a package.
#   python/sam/pretokengen/       the Lambda module: handler.py (edge) +
#                                 projection_governance_reader.py (read seam).
#   python/auth/                  the shared auth closure the handler imports:
#                                   cognito_utils.py        (_normalize_tenants_claim,
#                                                            ROLE_PERMISSIONS — stdlib only)
#                                   entitlement_claim_codec.py (CLAIM_NAME/encode — stdlib only)
#                                   entitlement_resolver.py (resolve_entitlement — imports
#                                                            only auth.cognito_utils)
#                                 + an `auth/__init__.py`. These 3 files are the
#                                 FULL `auth.*` closure the handler touches; the
#                                 rest of backend/src/auth is NOT vendored.
#   python/services/              the shared services the handler + reader import:
#                                   dynamodb_client.py   (fail-fast boto3 client)
#                                   projection_schema.py (key shape + table resolver;
#                                                         imports services.dynamodb_client)
#                                   module_registry.py   (MODULE_REGISTRY; `flask` is
#                                                         LAZY-imported inside its Flask-only
#                                                         functions, so importing the module
#                                                         needs NO Flask — see the note in
#                                                         backend/src/services/module_registry.py)
#                                 + a `services/__init__.py` shim. These 3 files
#                                 are the full `services.*` closure; the whole
#                                 backend services package is NOT vendored
#                                 (least-surface).
#   the shared auth runtime deps  PyJWT / cryptography / requests, pip-installed
#                                 as manylinux2014 / cp311 wheels (see below).
#
# boto3 is NOT vendored — the Lambda python3.11 runtime already provides it.
#
# NOTE on the handler's `sys.path.insert(0, backend/src)`: handler.py inserts a
# `backend/src` path at import time for local/CI test layouts. In the LAYER
# layout the vendored `auth/` + `services/` trees sit directly under `python/`
# (already on sys.path), so `import auth.*` / `import services.*` resolve from
# there regardless; the insert of a (non-existent-in-Lambda) `backend/src` path
# is a harmless no-op. The vendoring is what makes the imports work.
#
# Paths: this Makefile lives at sam/pretokengen/layer/Makefile, so the repo root
# is three levels up. Everything is copied read-only into the artifacts dir; the
# source tree is never mutated.

# sam/pretokengen/layer -> sam/pretokengen -> sam -> repo root
REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../../..)
SAM_SRC   := $(REPO_ROOT)/sam
AUTH      := $(REPO_ROOT)/backend/src/auth
SERVICES  := $(REPO_ROOT)/backend/src/services
# Python for the pip install. `sam build` runs make in a CLEAN env: bare `python`
# is absent and `/usr/bin/python3` (system) has no pip. The repo backend venv
# interpreter HAS pip, so prefer it deterministically whenever it exists on disk
# — independent of any inherited `PYTHON`/PATH (a plain `?=` is skipped when
# `PYTHON` is inherited from the env, which previously ran the pip-less system
# interpreter). Only when that venv is absent (prod/CI on another machine) do we
# honour a caller-supplied `PYTHON`, falling back to `python3`.
VENV_PYTHON := $(REPO_ROOT)/backend/.venv/bin/python
PYTHON      ?= python3
PYTHON      := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),$(PYTHON))

build-PreTokenGenLayer:
	@echo "Building PreTokenGenLayer from $(REPO_ROOT)"
	mkdir -p "$(ARTIFACTS_DIR)/python/sam"
	mkdir -p "$(ARTIFACTS_DIR)/python/auth"
	mkdir -p "$(ARTIFACTS_DIR)/python/services"
	# --- sam namespace package + the pretokengen module ------------------------
	# NOTE on the pretokengen copy: `sam build` stages this layer INTO
	# `sam/pretokengen/.aws-sam/build/PreTokenGenLayer/`, i.e. the artifacts dir
	# is a DESCENDANT of `$(SAM_SRC)/pretokengen`. A plain
	# `cp -r sam/pretokengen <artifacts>` therefore tries to copy a directory
	# into itself and fails (`cp: cannot copy a directory into itself`). We use
	# `rsync` with excludes so the copy skips the build tree (`.aws-sam`) plus
	# cache cruft — the source tree is still only read, never mutated.
	cp "$(SAM_SRC)/__init__.py" "$(ARTIFACTS_DIR)/python/sam/__init__.py"
	# Vendor ONLY the runtime Python of the module — exclude this app's own build
	# artifacts (the SAM template + the layer/function packaging dirs) and the
	# build tree / cache, so the layer carries just handler.py +
	# projection_governance_reader.py + __init__.py (least-surface). The excludes
	# also skip the `.aws-sam` DESCENDANT (this staging dir), avoiding the
	# copy-into-itself error `cp -r` would hit.
	rsync -a \
		--exclude '.aws-sam' --exclude '__pycache__' --exclude 'tests' \
		--exclude 'template.yaml' --exclude 'layer' --exclude 'function' \
		"$(SAM_SRC)/pretokengen/" "$(ARTIFACTS_DIR)/python/sam/pretokengen/"
	# --- the shared auth closure the handler imports (least-surface) -----------
	# cognito_utils: _normalize_tenants_claim + ROLE_PERMISSIONS (stdlib only).
	# entitlement_claim_codec: CLAIM_NAME + encode_entitlements (stdlib only).
	# entitlement_resolver: resolve_entitlement (imports only auth.cognito_utils).
	# These 3 files are the FULL auth.* closure the handler touches.
	cp "$(AUTH)/cognito_utils.py"           "$(ARTIFACTS_DIR)/python/auth/cognito_utils.py"
	cp "$(AUTH)/entitlement_claim_codec.py" "$(ARTIFACTS_DIR)/python/auth/entitlement_claim_codec.py"
	cp "$(AUTH)/entitlement_resolver.py"    "$(ARTIFACTS_DIR)/python/auth/entitlement_resolver.py"
	printf '"""Vendored auth shim: only the entitlement resolver/codec + cognito_utils closure is shipped in the PreTokenGen layer."""\n' \
		> "$(ARTIFACTS_DIR)/python/auth/__init__.py"
	# --- the shared services the handler + reader import (least-surface) -------
	# dynamodb_client: fail-fast boto3 client. projection_schema: key shape +
	# table resolver (imports services.dynamodb_client). module_registry:
	# MODULE_REGISTRY (flask is lazy-imported inside its Flask-only functions, so
	# importing the module here needs no Flask). These 3 files are the full
	# services.* closure the module touches.
	cp "$(SERVICES)/dynamodb_client.py"   "$(ARTIFACTS_DIR)/python/services/dynamodb_client.py"
	cp "$(SERVICES)/projection_schema.py" "$(ARTIFACTS_DIR)/python/services/projection_schema.py"
	cp "$(SERVICES)/module_registry.py"   "$(ARTIFACTS_DIR)/python/services/module_registry.py"
	printf '"""Vendored services shim: only dynamodb_client / projection_schema / module_registry are shipped in the PreTokenGen layer."""\n' \
		> "$(ARTIFACTS_DIR)/python/services/__init__.py"
	# --- install the shared auth runtime deps (PyJWT / cryptography / requests) -
	# Install as Lambda-PLATFORM manylinux wheels. cryptography (via PyJWT RS256)
	# ships a compiled Rust extension; a host-built (WSL Ubuntu, newer glibc)
	# wheel fails in the Amazon Linux Lambda container with "GLIBC_2.28 not
	# found". Pin to the Lambda runtime platform (manylinux2014 / glibc 2.17,
	# cp311) and binary-only so pip fetches a runtime-compatible wheel rather than
	# compiling against the host.
	$(PYTHON) -m pip install \
		--platform manylinux2014_x86_64 \
		--implementation cp \
		--python-version 3.11 \
		--only-binary=:all: --upgrade \
		-r "$(SAM_SRC)/shared/requirements.txt" \
		-t "$(ARTIFACTS_DIR)/python"
	# --- drop test/cache cruft so the layer stays lean --------------------------
	find "$(ARTIFACTS_DIR)/python" -type d -name '__pycache__' -prune -exec rm -rf {} + || true
	find "$(ARTIFACTS_DIR)/python" -type d -name 'tests' -prune -exec rm -rf {} + || true
