# S5b Local Walkthrough — Members runnable + clickable in the myAdmin SPA

This is the **runnable + clickable** acceptance walkthrough for S5b (Requirements
**R9.1**, **R9.3**). From a clean start it brings up the full local stack, onboards
`h-dcn` through the governance projection, and steps a human through the Leden Overzicht
feature surface: **filter → view → edit → add → transition (single + bulk) → export**.

> **Definition of done** (R9.1): a human starts the stack, logs in, and *operates* Leden
> Overzicht against real projected/seeded data — not merely "tests pass".

- **This is task 22.1** (author the walkthrough). Running it end-to-end and recording the
  scoped-vs-all comparison is **task 22.2** (`[H]`, human-run).
- **Long-running processes** (`docker compose up`, `sam local start-api`, `npm start`)
  are started in the **background** via `control_bash_process` or by the operator —
  **never** as foreground blocking commands (R9.3, `41-shell-environment.md`,
  `42-local-dynamodb-testing.md`).
- **Onboarding cross-reference.** The SysAdmin/Tenant-Admin production onboarding path
  (create tenant, entitle `MEMBERS`, define roles, assign roles, author tenant params) is
  documented in the spec's `requirements.md` R3 and `design.md` C12 — not duplicated here.
  Locally, the one-shot `onboard-hdcn-local.py` script writes the same MySQL rows those
  endpoints would (see step 2).

---

## 1. Prerequisites + local topology

You need: native **WSL Docker** (not Docker Desktop), the backend virtualenv at
`backend/.venv`, Node/npm for the frontend, and the AWS SAM CLI (`sam`).

### Topology

Everything runs on one Docker network, `myadmin-local`. In-network containers reach
DynamoDB Local at `dynamodb-local:8000`; host scripts reach it at `localhost:8000`.

| Component | Host address | In-network alias | Notes |
| --- | --- | --- | --- |
| DynamoDB Local | `localhost:8000` | `dynamodb-local:8000` | `amazon/dynamodb-local`, `-sharedDb`; holds both `test_governance_projection` and `sam-members-local` |
| Flask backend | `localhost:5000` | — | auth context, tenant list, Tenant Admin, other modules |
| MySQL | (compose service) | — | single system of record for governance/params |
| Vite (SPA) | `localhost:3000` | — | `npm start` |
| Members SAM API | `127.0.0.1:3001` | joins `myadmin-local` | `sam local start-api`; the SPA targets this via `VITE_MEMBERS_API_BASE_URL` |

The SPA talks to the Flask backend for everything except Members; **Members traffic goes
straight to the Members SAM API** (`http://127.0.0.1:3001`, set in `frontend/.env.local`
as `VITE_MEMBERS_API_BASE_URL`). Both DynamoDB tables live in the same local DynamoDB.

---

## 2. Bring-up steps (in order)

### Step 2.0 — Start Docker: `myadmin-local` + DynamoDB Local + backend + MySQL

Start the stack **in the background** (via `control_bash_process` / operator). The
compose stack brings up `dynamodb-local`, the Flask backend, and MySQL on the
`myadmin-local` network:

```bash
docker compose up
# (or just the datastore: docker compose up dynamodb-local)
```

The backend service has `AWS_ENDPOINT_URL_DYNAMODB=http://dynamodb-local:8000` set for
it; host scripts default to `http://localhost:8000`. Wait until the backend answers on
`localhost:5000` and DynamoDB Local answers on `localhost:8000` before continuing.

> **Fail-fast note.** The projection DynamoDB client requires
> `GOVERNANCE_PROJECTION_TABLE` and `AWS_REGION`; the local endpoint override is used
> **only** when `AWS_ENDPOINT_URL_DYNAMODB` is set. There is no hidden `localhost` default
> that could point projection work at production (`42-local-dynamodb-testing.md`).

### Step 2.1 — Seed / onboard `h-dcn` locally

Run the one-shot local onboarding script (short-lived, so a normal foreground run is
fine):

```bash
backend/.venv/bin/python scripts/local/onboard-hdcn-local.py
```

This is idempotent, touches **no AWS/prod**, and does four things:

1. **Seeds MySQL tenant params** for `h-dcn`: `members.scope_dimensions` (dimension
   `region`, values **Noord / Zuid / Oost / West**, `all_wildcard=Regio_All`,
   `required_for=[Members_CRUD]`) + `members.field_overlay` (a small variable field,
   `motor_type`).
2. **Ensures `webmaster@h-dcn.nl` holds `Regio_All`** (all-access) in `user_tenant_roles`,
   so its projected scope grant is `["*"]` — the general-admin path.
3. **Creates `test_governance_projection`** in DynamoDB Local and runs the **real**
   `ProjectionSync` for `h-dcn`, projecting `module#members`, `config#scope`,
   `config#fields`, and the `scopegrant#` rows into the tenant partition.
4. **Creates `sam-members-local`** and seeds `h-dcn`'s **membership-type catalog**
   (`regulier`, `erelid`, `jeugd` — all active) plus members across **Noord / Zuid /
   West** so Leden Overzicht shows data.

> Expected result: the script prints the projected rows for the `h-dcn` partition and
> confirms the membership types + members were seeded.

### Step 2.2 — Build + run the Members SAM module

From `sam/members`, build the function + layer, then start the local API **in the
background** (`control_bash_process` / operator):

```
sam build
sam local start-api --port 3001 --docker-network myadmin-local --env-vars env-vars.local.json
```

- `--docker-network myadmin-local` lets the Lambda reach `dynamodb-local:8000`.
- `--env-vars env-vars.local.json` supplies `MEMBERS_TABLE=sam-members-local`,
  `GOVERNANCE_PROJECTION_TABLE=test_governance_projection`,
  `AWS_ENDPOINT_URL_DYNAMODB=http://dynamodb-local:8000`, the `h-dcn` local Cognito
  issuer, and the two **local-only auth-fallback flags** (see the auth note below).
- The API listens on `127.0.0.1:3001`, which matches `VITE_MEMBERS_API_BASE_URL` in
  `frontend/.env.local`.

> Expected result: `sam local start-api` reports it is mounting `ANY /{proxy+}` and
> listening on port 3001. A quick health check: `GET http://127.0.0.1:3001/members`
> returns a JSON envelope (`{"data": [...]}`) once you have a token.

### Step 2.3 — Start the frontend

Start Vite **in the background** (`control_bash_process` / operator):

```bash
cd frontend && npm start
```

> Expected result: Vite serves the SPA on `http://localhost:3000`.

### Local-dev authentication note (local-only, prod-unreachable)

Local Cognito tokens carry `cognito:groups` but **no `custom:entitlements` claim** (there
is no PreTokenGen trigger on the local pool), so the module edge would otherwise 403. Two
**flag-gated** fallbacks make the local run work; both are **OFF in prod** (empty defaults
in `sam/members/template.yaml`) and are set only in `sam/members/env-vars.local.json`:

- `MEMBERS_LOCAL_AUTH_FALLBACK=true` — when `has_capability` returns "token doesn't
  answer", derive the capability from a `Members_*` group. It **never** softens a real
  `False` denial.
- `MEMBERS_LOCAL_TENANT_ID=h-dcn` — when the verified entitlement resolves no tenant, use
  this tenant instead of 403-ing.

Consequences for the login you use:

- The login user needs a **`Members_*` group** (e.g. `Members_CRUD`) for the capability
  fallback to grant. `webmaster@h-dcn.nl` is set up for this.
- **A fresh login is required after any group change** — the token is minted at login, so
  group edits only take effect on the next sign-in.
- **Known-benign backlog item.** Local dev currently points `HDCN_COGNITO_ISSUER` at the
  **prod Pool A** (`eu-west-1_Hdp40eWmu`), and `Members_CRUD` was added to
  `webmaster@h-dcn.nl` in that pool (reversible). The backlog is a "test-pool hygiene
  switch" to a non-prod dev pool. This does not block the walkthrough.

---

## 3. Click-through acceptance (the runnable + clickable definition of done, R9.1)

Log in to the SPA at `http://localhost:3000` as an `h-dcn` user in a `Members_*` group
(e.g. `webmaster@h-dcn.nl`). Ensure the tenant selector is on **h-dcn**. The
**Ledenadministratie / Leden Overzicht** entry appears in the main menu only because
`h-dcn` is entitled to `MEMBERS` (`hasMEMBERS` gate). Open it.

Step through each feature built in this spec, in order:

### 3.1 — Filter and sort

1. On Leden Overzicht, open the column filters (Table Filter Framework v2 headers).
2. Filter by **region** (Noord/Zuid/West), **status**, and **membership type**.
3. Click a sortable header to sort.

> **Expected:** the table narrows to matching rows and reorders on sort. The
> subgroup/region value shows as a `Badge` cell.

### 3.2 — Compact / full view switch

1. Toggle the compact/full view switch.

> **Expected:** the overlay columns (from the tenant field config, e.g. the `motor_type`
> variable field) appear in full view and disappear in compact view — driven by
> `GET /members/field-config`, not hard-coded.

### 3.3 — View (read-only) — row-click

1. Click a member row (no per-row buttons — row-click is the affordance).

> **Expected:** a **read-only** view modal opens with that member's detail
> (`GET /members/{member_id}`).

### 3.4 — Edit

1. In the view modal, click **Bewerken** (Edit) to open the edit modal.
2. Change a field; the **membership type** is a dropdown of **active-only** catalog
   entries (no free text).
3. Save.

> **Expected:** a `PUT /members/{member_id}` fires and the row updates in the table.

### 3.5 — Add

1. Click **Nieuw lid** (New member) in the header actions.
2. Fill the add / application modal (again, membership type is an active-only dropdown).
3. Save.

> **Expected:** a `POST /members` fires and the new member appears as a new row.

### 3.6 — Single transition

1. Open a member's view modal, click **Status wijzigen** (Change status).
2. Pick a target status — the allowed targets come from the module response, not the UI.
3. Confirm.

> **Expected:** a `POST /members/{member_id}/memberships/{membership_id}/transition`
> fires and the member's status updates.

### 3.7 — Bulk transition

1. Select several rows via their checkboxes; the bulk action bar appears.
2. Pick a target status for the selection and confirm.

> **Expected:** a `POST /memberships/transition` fires over the selected ids and the
> statuses update.

### 3.8 — Export

1. Click **Exporteren** (Export) in the header actions.

> **Expected:** a CSV of the currently scoped/filtered rows downloads.

### 3.9 — Scope check (R8.7)

The module edge authoritatively filters every view/modal/action to the caller's granted
subgroup:

- A **Noord-scoped** user (a subgroup-limited `region=Noord` grant) sees and acts on
  **only Noord** members.
- An **all-access** user (`Regio_All` → `["*"]`, e.g. `webmaster@h-dcn.nl`) sees **all**
  members across Noord/Zuid/West.

> This is the R8.7 scope demonstration. Running the scoped-vs-all comparison end-to-end
> and recording it for the S5 Go/No-Go MANUAL look & feel/UX item is **task 22.2**
> (`[H]`, human-run) — see R9.2.

---

## 4. Teardown

Stop the background processes in reverse order (`control_bash_process` `stop` / operator):
Vite, then `sam local start-api`, then the Docker stack. To drop just the projection
table between runs:

```bash
backend/.venv/bin/python scripts/local/teardown-dynamodb-local.py
```

Bring the whole stack down with `docker compose down` (or `docker compose stop
dynamodb-local` for just the datastore).

---

## 5. Known-benign items

- **Local pool coupling (backlog).** Local dev is coupled to prod Pool A; the fix is the
  test-pool hygiene switch to a non-prod dev pool (see the auth note). Reversible; not
  blocking.
- **Local auth fallback flags** (`MEMBERS_LOCAL_AUTH_FALLBACK`, `MEMBERS_LOCAL_TENANT_ID`)
  exist only for the local run and are prod-unreachable (empty defaults in the template).
- **Fresh login after group change** — token claims are minted at login; re-authenticate
  after editing a user's groups.
