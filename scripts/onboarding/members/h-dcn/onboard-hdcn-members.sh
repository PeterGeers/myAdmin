#!/usr/bin/env bash
# onboard-hdcn-members.sh - one-command h-dcn members onboarding/sync runner.
#
# Runs the full sequence so a repeat onboarding is a single invocation:
#   1. seed members config (MySQL scope_dimensions + field_overlay)
#   2. backfill DRY-RUN (fidelity + dedup pre-flight report)
#   3. backfill APPLY --reconcile (upsert + absence sweep)
#   4. post-verify duplicate check
#
# Usage:
#   AWS_PROFILE=nonprofit-deploy bash scripts/onboarding/members/h-dcn/onboard-hdcn-members.sh
#   SKIP_SEED=1 SKIP_DRY=1 bash scripts/onboarding/members/h-dcn/onboard-hdcn-members.sh
# Env overrides: TENANT (h-dcn), AWS_REGION (eu-west-1), MEMBERS_TABLE (sam-members), PY, SKIP_SEED, SKIP_DRY.
# Env overrides: TENANT (h-dcn), AWS_REGION (eu-west-1), MEMBERS_TABLE (sam-members),
#                PY (backend/.venv/bin/python), SKIP_SEED, SKIP_DRY.
set -euo pipefail

TENANT="${TENANT:-h-dcn}"
export AWS_REGION="${AWS_REGION:-eu-west-1}"
export MEMBERS_TABLE="${MEMBERS_TABLE:-sam-members}"
PY="${PY:-backend/.venv/bin/python}"
DIR="scripts/onboarding/members/h-dcn"
CFG="$DIR/members_config.json"

echo "================================================================"
echo " h-dcn members onboarding  (tenant=$TENANT region=$AWS_REGION table=$MEMBERS_TABLE)"
echo "================================================================"

if [ "${SKIP_SEED:-0}" != "1" ]; then
  echo "[1/4] Seeding members config (MySQL) ..."
  PYTHONPATH=backend/src "$PY" "$DIR/seed-hdcn-members-config.py" --tenant "$TENANT" --apply --config "$CFG"
fi

if [ "${SKIP_DRY:-0}" != "1" ]; then
  echo "[2/4] Backfill DRY-RUN + dedup pre-flight ..."
  "$PY" "$DIR/backfill-hdcn-members.py" --tenant "$TENANT" --members-config "$CFG" --reconcile --dedup
fi

echo "[3/4] Backfill APPLY --reconcile + dedup guard ..."
"$PY" "$DIR/backfill-hdcn-members.py" --tenant "$TENANT" --members-config "$CFG" --reconcile --dedup --apply

echo "[4/4] Done. Table synchronized for tenant=$TENANT."
