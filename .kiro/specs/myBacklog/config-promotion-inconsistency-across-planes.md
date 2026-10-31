# SPEC CANDIDATE: Secret & config management is inconsistent across planes
**Problem (observed 2026-10-10 during the Members mail/pivot prod release):** the SAME class of
problem — "how does a value (a secret, or a piece of config) get to the code that needs it" — is
solved with DIFFERENT tools in different parts of the codebase. There is no single documented
convention, so each plane/spec reinvented it. This makes rotation, auditing, and onboarding harder
and the differences are accidental, not designed.

## Concrete evidence — the OpenRouter API key alone is handled THREE ways
One secret, three mechanisms:
- **Flask / Railway plane:** `OPENROUTER_API_KEY` is a **Railway service variable**, read at runtime
  via `os.getenv(...)` (e.g. `backend/src/image_ai_processor.py`, `services/budget_ai_service.py`,
  `services/ai_template_assistant.py`, `pdf_ai_extraction.py`, `routes/sysadmin_health.py`). Declared
  in `backend/validate_env.py`.
- **SAM Members plane:** same key is a **GitHub Actions repo secret** → passed by
  `deploy-sam-members.yml` as a CloudFormation **`NoEcho` template parameter** (`OpenRouterApiKey`,
  `sk-or-v1-` AllowedPattern) → wired into the Lambda **env var** `OPENROUTER_API_KEY`
  (`sam/members/template.yaml`), read fail-fast by `sam/members/domain/ai_improve.py`.
- **Frontend:** surfaces the "Improve with AI" button only; holds NO key — calls the SAM API
  (`POST /members/templates/{id}/ai-improve`). (Correct — a browser must never hold the key.)

Note: we are **NOT** using AWS Secrets Manager / SSM SecureString anywhere for this — the SAM key
lives as a Lambda env var (in the function config + CFN deploy history), not fetched at runtime.

## The broader pattern to inventory (same "different tools, same problem" smell)
- **Secrets at rest:** Railway vars vs GitHub secrets vs CFN NoEcho→Lambda env vs (nowhere) AWS
  Secrets Manager/SSM. Which should be canonical? When is Secrets Manager worth the IAM/rotation cost?
- **Non-secret config/env selection:** Flask `.env` + `DB_*`/`APP_ENV` resolver; SAM `samconfig.toml`
  `[test]`/`[prod]` parameter_overrides; frontend `VITE_*` build-time env. Three env-selection models.
- **Tenant config values:** MySQL `parameters` table (namespace/scope/scope_id) projected into
  DynamoDB `config#*` rows — vs the above. (This release even needed a manual local→Railway copy of
  5 `members.*` rows because config authored in TEST never reached PROD — a symptom of no convention
  for "promote tenant config between environments".)

## Why a spec later, not a fix now
Converging these is cross-cutting (Flask + SAM + frontend + IAM + steering) and risky to retrofit on
a live secret path. Scope it deliberately:
1. **Inventory** every secret + config value and how each is sourced per plane (read-only sweep:
   `validate_env.py`, Railway vars, all `samconfig.toml`, `template.yaml` params, `VITE_*`, any
   Secrets Manager/SSM usage).
2. **Decide the canonical tool(s)** per category (runtime secret / deploy secret / env selection /
   tenant config promotion) and write it into steering.
3. **Migrate the outliers** incrementally; don't big-bang the prod secret path.

Relates to: steering `43-cicd-deploys.md` ("no secrets in CI"), `41-shell-environment.md` + the
`#database` skill (env model), and possibly the open `.kiro/specs/Members/Parameter redesign/`
analysis. Also connects to the open "s3 object management module and SAM" + shared-building-blocks
backlog items (same reuse-across-planes theme).
