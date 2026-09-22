# Makefile builder for the Members Lambda layer (S5b C11 / task 1.1).
#
# `sam build` invokes the `build-MembersLayer` target with $(ARTIFACTS_DIR) set to
# the layer's staging dir. A Python Lambda layer exposes its packages under
# `python/` on `sys.path`, so this target assembles exactly the three things the
# module imports at runtime — and nothing else — under `$(ARTIFACTS_DIR)/python`:
#
#   python/sam/shared/     the vendored module-plane shared auth toolkit
#                          (get_verified_claims / has_capability / entitlement codec)
#   python/sam/members/    the Members module (handler edge + domain + repository +
#                          tenants), i.e. everything `sam.members.handler.app.handler`
#                          transitively imports
#   python/sam/__init__.py the `sam` namespace package so `import sam.shared` /
#                          `import sam.members` resolve as packages
#   python/services/       the shared `dynamodb_client` + `projection_schema` (the only
#                          `services.*` names the module imports: table_design.py needs
#                          dynamodb_client; projection_config_reader.py needs
#                          projection_schema, which itself needs dynamodb_client), plus
#                          an `__init__.py` — deliberately NOT the whole
#                          backend/src/services package (least-surface vendoring).
#
# Paths: this Makefile lives at sam/members/layer/Makefile, so the repo root is three
# levels up. Everything is copied read-only into the artifacts dir; the source tree is
# never mutated.

# sam/members/layer -> sam/members -> sam -> repo root
REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../../..)
SAM_SRC   := $(REPO_ROOT)/sam
SERVICES  := $(REPO_ROOT)/backend/src/services
# Python for the pip install. `sam build` runs make in a CLEAN env: bare `python`
# is absent and `/usr/bin/python3` (system) has no pip.
#
# ROOT CAUSE of the earlier "`/usr/bin/python3: No module named pip`" failure: a plain
# `PYTHON ?= ...` is skipped whenever a `PYTHON` value is INHERITED from the environment
# (make treats an env-provided var as already set for `?=`). If `sam build` was launched
# from a shell that exported `PYTHON` (or exported it empty), the venv default never
# applied and make ran the pip-less system interpreter. So we do NOT rely on `?=` alone.
#
# The repo's backend venv interpreter HAS pip, so prefer it deterministically whenever it
# exists on disk — independent of any inherited `PYTHON`/PATH. Only when that venv is
# absent (prod/CI on another machine) do we honour a caller-supplied `PYTHON`, falling back
# to `python3`. Override for a venv elsewhere with `make PYTHON=/path/to/py` AND no repo
# venv present, or point the repo venv at your interpreter.
VENV_PYTHON := $(REPO_ROOT)/backend/.venv/bin/python
PYTHON      ?= python3
# `$(wildcard ...)` is non-empty only if the venv python actually exists; when it does, it
# wins over any inherited PYTHON so the pip-bearing interpreter is always used locally.
PYTHON      := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),$(PYTHON))

build-MembersLayer:
	@echo "Building MembersLayer from $(REPO_ROOT)"
	mkdir -p "$(ARTIFACTS_DIR)/python/sam"
	mkdir -p "$(ARTIFACTS_DIR)/python/services"
	# --- sam namespace package + shared + members ------------------------------
	# NOTE on the members copy: `sam build` stages this layer INTO
	# `sam/members/.aws-sam/build/MembersLayer/`, i.e. the artifacts dir is a
	# DESCENDANT of `$(SAM_SRC)/members`. A plain `cp -r sam/members <artifacts>`
	# therefore tries to copy a directory into itself and fails
	# (`cp: cannot copy a directory into itself`). We use `rsync` with excludes so
	# the copy skips the build tree (`.aws-sam`) plus cache/test cruft — the source
	# tree is still only read, never mutated.
	cp "$(SAM_SRC)/__init__.py" "$(ARTIFACTS_DIR)/python/sam/__init__.py"
	rsync -a --exclude '.aws-sam' --exclude '__pycache__' --exclude 'tests' \
		"$(SAM_SRC)/shared/"  "$(ARTIFACTS_DIR)/python/sam/shared/"
	rsync -a --exclude '.aws-sam' --exclude '__pycache__' --exclude 'tests' \
		"$(SAM_SRC)/members/" "$(ARTIFACTS_DIR)/python/sam/members/"
	# --- the shared services the module imports at runtime (least-surface) -----
	# dynamodb_client: the fail-fast boto3 client (repository/table_design.py).
	# projection_schema: the governance projection key-shape + table resolver
	#   (repository/projection_config_reader.py — S5b task 8.1). It imports only
	#   stdlib + services.dynamodb_client, so these two files are the full closure
	#   of the `services.*` names the module touches; the whole backend services
	#   package is deliberately NOT vendored.
	cp "$(SERVICES)/dynamodb_client.py" "$(ARTIFACTS_DIR)/python/services/dynamodb_client.py"
	cp "$(SERVICES)/projection_schema.py" "$(ARTIFACTS_DIR)/python/services/projection_schema.py"
	printf '"""Vendored services shim: only dynamodb_client is shipped in the Members layer."""\n' \
		> "$(ARTIFACTS_DIR)/python/services/__init__.py"
	# --- install the shared auth runtime deps (PyJWT / cryptography / requests) -
	# Install the shared auth runtime deps as Lambda-PLATFORM manylinux wheels.
	# cryptography (via PyJWT RS256) ships a compiled Rust extension; a host-built
	# (WSL Ubuntu, newer glibc) wheel fails in the Amazon Linux Lambda container with
	# "GLIBC_2.28 not found". Pin to the Lambda runtime platform (manylinux2014 /
	# glibc 2.17, cp311) and binary-only so pip fetches a runtime-compatible wheel
	# rather than compiling against the host.
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
