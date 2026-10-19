# Security Assessment — 2026-10-19

Run of `.kiro/specs/code-quality-maintenance/prompts/prompt-security.md`.
Seeded (Step 0) by the automated CodeQL code-scanning alerts on `main`, then the three
manual perspectives (Security Architect / Red Team / Risk Manager) over **both planes**
(Flask/MySQL and SAM/DynamoDB).

> **Scope note.** The CodeQL seed is factual and authoritative (it is GitHub's own
> scan output). The three manual perspectives below are a *desk review* framed around the
> architecture + the seed — they flag risk areas and point at the seed findings; they are
> not a substitute for a full manual pentest. Items explicitly marked "unverified" were
> not confirmed against running code in this pass.

---

## Step 0 — CodeQL seed (authoritative, automated)

Source: `gh api repos/PeterGeers/myAdmin/code-scanning/alerts?ref=refs/heads/main&state=open`
captured 2026-10-19.

### Totals

| Severity | Count |
| --- | --- |
| High | 17 |
| Medium | 83 |
| **Total open on `main`** | **100** |

> CodeQL reports `high`/`medium`/`low`. Mapped to this spec's bands: **High → High**,
> **Medium → Medium**. No `critical`/`low` CodeQL bands present this run.

### By rule (grouped — most are ONE repeated pattern)

| Rule | Count | Sev | Plane | Domain (perspective 1) |
| --- | --- | --- | --- | --- |
| `py/stack-trace-exposure` | 79 | medium | Flask | Logging & error-handling |
| `py/incomplete-url-substring-sanitization` | 8 | high | Flask (mostly **tests**) | Input validation |
| `actions/missing-workflow-permissions` | 4 | medium | CI | Supply chain / infra |
| `py/path-injection` | 3 | high | Flask | Data security (file paths) |
| `py/polynomial-redos` | 2 | high | Flask | Availability (ReDoS) |
| `js/xss-through-dom` | 2 | high | Frontend | API/data security (XSS) |
| `js/insecure-randomness` | 1 | high | Frontend | Crypto |
| `py/clear-text-logging-sensitive-data` | 1 | high | Script | Logging & auditing |

### High-severity alerts — exact locations (the 17 that matter first)

**`js/insecure-randomness` (1)**
- `frontend/src/components/public/application/ApplicationFormPage.tsx:138` — `Math.random()` in a session-key fallback. **A fix is already staged in the working tree** (replaced with `crypto.getRandomValues`); not yet committed.

**`js/xss-through-dom` (2)**
- `frontend/src/components/members/analytics/MemberMailCompose.tsx:610`
- `frontend/src/components/members/analytics/MemberMailCompose.tsx:741`
- Context: a `dangerouslySetInnerHTML={{ __html: previewBodyHtml }}` mail-preview pane. Needs the preview HTML sanitized (e.g. DOMPurify) before render.

**`py/path-injection` (3)**
- `backend/src/file_cleanup_manager.py:238`, `:239`, `:245` — a local path derived from `file_url` is passed to `os.path.exists` / `os.access` / `os.chmod` without confirming it stays inside an allowed base dir. Needs canonicalization + base-dir containment check.

**`py/polynomial-redos` (2)**
- `backend/src/routes/landing_page_routes/public_endpoints.py:61`, `:65` — regexes in the public contact-form sanitizer (`re.sub(r"<[^>]*>", "", value)` and friends) on a **public, unauthenticated** endpoint. ReDoS on untrusted input = availability risk. Replace with a non-backtracking strip or a bounded parser.

**`py/clear-text-logging-sensitive-data` (1)**
- `scripts/onboarding/members/_generic/load-cognito-users.py:519` — prints generated throwaway passwords to stdout. Dev/test onboarding script; lower blast radius but still a cleartext-secret log. Gate behind an explicit `--show-passwords` flag or write to a restricted file.

**`py/incomplete-url-substring-sanitization` (8)** — **7 of 8 are in test files**
- `backend/tests/unit/test_invoice_service_s3_upload.py:222`
- `backend/tests/unit/test_landing_page_publish_service.py:1490,1502,1522,1532,1542`
- `backend/tests/unit/test_landing_page_styles.py:314`
- `backend/tests/unit/test_dynamodb_client.py:99`
- These are URL-substring checks (e.g. `"host" in url`) in **tests**, so production exposure is limited — but the same anti-pattern in a test often mirrors a product helper. Verify none of the asserted helpers ship the same check.

### Medium — the one big cluster

`py/stack-trace-exposure` ×79 across the Flask routes (`admin_routes.py`, `str_routes.py`,
the `landing_page_routes/*` and `media_asset_routes/*` packages, `tenant_admin_*`,
`sysadmin_roles.py`, `reporting_routes.py`, `aangifte_ib_routes.py`, …). This is a **single
repeated pattern**: `except Exception as e: return jsonify({'error': str(e)}), 500` leaks
internal exception text to the client. Fixable uniformly (log server-side, return a generic
message). This also directly collides with the API-conventions rule
(`30-backend-api-flask-mysql`) whose error shape returns `str(e)` — so the convention itself
should be revisited (see Lessons).

`actions/missing-workflow-permissions` ×4 in `.github/workflows/full-test-suite.yml` — jobs
without an explicit least-privilege `permissions:` block. Add `permissions: contents: read`
(plus only what each job needs).

---

## 1. Security Architect — per-domain status

| Domain | Status | Notes (seed-linked) |
| --- | --- | --- |
| Authentication (Cognito JWT) | matig | Flask plane decodes JWT without JWKS signature verification (E1, carried from prior runs). SAM plane verifies properly at the edge. |
| Authorization (RBAC) | matig | No CodeQL hits; carried architectural items (SysAdmin bypass, 5-min role cache). |
| Multi-tenant isolation | goed/matig | No new CodeQL cross-tenant finding; SAM `tenant_id`+`LeadingKeys` model sound. Unverified: every Flask route's `administration` filter. |
| API / data security | **zwak (high)** | `js/xss-through-dom` ×2 (mail preview), `py/path-injection` ×3 (file cleanup). Both real highs. |
| Availability | **matig (high)** | `py/polynomial-redos` ×2 on a public endpoint. |
| Crypto | matig | `js/insecure-randomness` ×1 (fix staged). |
| Logging & auditing | **zwak** | `py/stack-trace-exposure` ×79 + `py/clear-text-logging-sensitive-data` ×1. The dominant debt. |
| Infrastructure / supply chain | matig | `actions/missing-workflow-permissions` ×4; Terraform state in repo (carried). |
| SAM edge / tenancy / PreTokenGen | goed | No CodeQL hits on `sam/`. Model matches ADR 0007. Unverified by dynamic test this pass. |

## 2. Red Team — attack paths (seed-prioritised)

- **ReDoS on the public contact form** (`public_endpoints.py:61/65`): unauthenticated attacker sends a crafted long string to the contact endpoint → catastrophic regex backtracking → worker starvation. Precondition: none (public). Impact: availability. Detection: none currently. Mitigation: bounded/linear sanitizer.
- **Stored/DOM XSS via mail preview** (`MemberMailCompose.tsx:610/741`): a composer with crafted HTML in subject/body → `dangerouslySetInnerHTML` renders it in the preview (and possibly the sent mail). Precondition: authenticated member-admin. Impact: XSS in-app, and malicious HTML delivered to recipients. Mitigation: sanitize before render + before send.
- **Path traversal in file cleanup** (`file_cleanup_manager.py:238-245`): if `file_url`→`local_path` is attacker-influenceable, `os.chmod(local_path, 0o666)` could loosen perms on an arbitrary path. Precondition: control over a stored `file_url`. Impact: integrity. Mitigation: containment check against an allowed base dir.
- **Info leak via stack traces** (×79): any error path returns `str(e)` → attacker maps internals (table names, file paths, library versions) to plan deeper attacks. Precondition: ability to trigger an error (often trivial). Impact: recon amplifier. Mitigation: generic error bodies.

## 3. Risk Manager — register (high items)

| # | Risk | Cat | Impact | Kans | Score | Mitigatie |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | ReDoS public contact form | Availability | 4 | 3 | 12 | Linear sanitizer |
| R2 | DOM XSS mail preview | Data Integrity | 4 | 3 | 12 | DOMPurify |
| R3 | Path injection file cleanup | Infrastructure | 4 | 2 | 8 | Base-dir containment |
| R4 | Stack-trace exposure ×79 | Compliance/Info | 3 | 4 | 12 | Generic error contract |
| R5 | Cleartext password log (script) | Compliance | 3 | 2 | 6 | Flag-gate the print |
| R6 | Insecure randomness (staged) | Authentication | 2 | 2 | 4 | Fix staged — commit it |
| R7 | CI jobs missing `permissions:` | Supply Chain | 3 | 2 | 6 | Least-priv perms block |

CodeQL-seed counts are reported separately from manually-surfaced items above: **all R1–R7
originate from the automated seed.** No additional *new* manual-only high was found this pass.

---

## Comparison with previous run (`security-assessment-2026-09-26`)

The prior assessment (`security-assessment-2026-09-26`) was an **OIDC deploy-role trust
audit** — a narrow, manual scope — and did **not** ingest CodeQL code-scanning alerts (no
prompt did until this run). So there is **no prior CodeQL baseline** to diff against; this
run establishes the baseline: **100 open (17 high / 83 medium)**.

Next run should diff per-rule counts against this file to confirm the numbers trend down.

## Lessons / Recurring Issues

- **The `str(e)` error contract is itself the source of 79 alerts.** The API-conventions
  steering (`30-backend-api-flask-mysql`) prescribes `return jsonify({'success': False,
  'error': str(e)}), 500`. That pattern is exactly what `py/stack-trace-exposure` flags.
  Fixing the 79 sites without changing the convention will regress — **update the convention
  first** (log full error server-side, return a generic/caller-safe message + an error id),
  then sweep the routes. This is the single highest-leverage change.
- **CodeQL was invisible to the maintenance loop** until this run. Keep running
  `prompt-security.md` after every merge to `main` so the 100 doesn't silently grow.
- **Most URL-sanitization highs are in tests** — fix, but verify the product helpers they
  assert against don't share the substring-check anti-pattern.
