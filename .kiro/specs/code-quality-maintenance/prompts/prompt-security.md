# Security Assessment Prompts — myAdmin

Drie perspectieven voor een grondige security-analyse van myAdmin:

1. Security Architect (beoordeling)
2. Red Team (aanvalspaden)
3. Risk Manager (beheer en prioritering)

---

## 1. Security Architect — Beoordeling

Analyseer de security-architectuur van myAdmin alsof je een senior security architect bent.

### Architectuur-context

myAdmin is een multi-tenant SaaS-platform voor financiële administratie en short-term rental beheer. Het draait op **TWEE planes** met verschillende auth-, tenancy- en opslagmodellen — beoordeel beide.

**Plane 1 — Flask / MySQL plane (`backend/`):**

- Backend: Python Flask + Waitress, MySQL 8.0, Docker
- Frontend: React 19 + TypeScript, Vite
- Auth: AWS Cognito (JWT), per-tenant RBAC via `cognito_required` + `tenant_required` decorators
- Externe APIs: OpenRouter AI (factuurextractie), Google Drive (opslag), AWS SNS (notificaties), AWS SES (e-mail)
- Infra: Docker Compose (dev), Railway (productie), Terraform (AWS resources)
- Credentials: Fernet-encrypted in MySQL, master key via `CREDENTIALS_ENCRYPTION_KEY` env var

**Plane 2 — SAM / module plane (`sam/`):** React → API Gateway → Lambda → DynamoDB (migrerende modules; Members eerst, dan Events/Webshop). Dit is een APART platform met een EIGEN security-model — behandel het niet als "backend":

- **Auth:** GEVERIFIEERDE Cognito-JWT aan de Lambda-edge (`sam/shared` toolkit: `get_verified_claims`/`get_groups`, `get_entitlements`/`has_capability`) — cryptografisch geverifieerd tegen Cognito JWKS. Dit verschilt fundamenteel van de Flask-plane (zie risico E1).
- **Tenancy:** `tenant_id` als DynamoDB partition key + IAM `dynamodb:LeadingKeys`, afgedwongen in de **repository-laag** (één plek). De actieve tenant is een PER-REQUEST selectie: de client stuurt `X-Tenant`, de edge valideert dat die in de geverifieerde entitlement `tenant_keys` zit (de header SELECTEERT onder geverifieerde tenants, GRANT nooit een tenant → geen match = 403). Zie ADR 0007.
- **Entitlements:** een Pre-Token-Generation Lambda (`sam/pretokengen`) mint de `custom:entitlements` claim op het token bij cold start/login — een authz-integriteit-kroonjuweel.
- **Opslag:** DynamoDB (GEEN MySQL, GEEN `DatabaseManager`). Tabellen heten `sam-<module>[-<env>]`, resolved uit een per-module env var (fail-fast, nooit hardcoded). Module-plane IAM scoped naar `sam-*` (defense in depth boven `LeadingKeys`).
- **Layering als control:** handler = dunne adapter (parse → authenticate/tenant-context → authorize → delegate → respond); de **repository is de ENIGE DynamoDB-touchpoint** en waar tenant-scoping leeft. Een handler die de repository omzeilt of logic bevat is een security-smell.
- **AWS-accounts (cross-account):** identity/Cognito in `personal` (344561557829, eu-west-1); infra/data (DynamoDB/API GW/Lambda) in `nonprofit-deploy` (506221081911). Zie `23-aws-accounts.md`.
- **Deploy:** via OIDC CI-workflow + committed `samconfig.toml` (`sam deploy --config-env <env>`) — nooit hand-getypte `--parameter-overrides`/`--stack-name`.

**Tenant-isolatie:**

- JWT bevat `custom:tenants` claim
- Elke tenant-scoped tabel heeft `administration` kolom
- `tenant_required()` decorator valideert tenant-access op route-niveau
- `add_tenant_filter()` helper voor SQL queries
- SysAdmin bypass via `allow_sysadmin=True` parameter

**Authenticatie & autorisatie:**

- AWS Cognito User Pool met groepen (Administrators, Tenant_Admin, Finance_CRUD, STR_CRUD, etc.)
- JWT-tokens gedecodeerd in backend (base64 payload, expiry check)
- Per-tenant rollen uit `user_tenant_roles` tabel, gecached 5 min
- Permission mapping: `ROLE_PERMISSIONS` dict → `validate_permissions()` check

**API-beveiliging:**

- Flask-CORS met credentials support
- Rate limiting op signup routes
- Security middleware: suspicious pattern detection (SQLi, XSS, traversal)
- Security headers: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
- File uploads: `secure_filename()`, extensie-whitelist, 100MB max

**Data security:**

- Database: parameterized queries via `%s` placeholders
- Google Drive credentials: AES-256 encrypted in MySQL
- Env vars voor alle secrets (nooit hardcoded)
- Password reset: cryptographically secure 6-digit code, 10 min expiry, max 3 attempts

### Beoordeel specifiek

| Domein                | Controleer                                                                                   |
| --------------------- | -------------------------------------------------------------------------------------------- |
| Authenticatie         | Cognito JWT validatie, token expiry, refresh flow                                            |
| Autorisatie           | RBAC granulariteit, permission escalation paths, SysAdmin bypass                             |
| Multi-tenant isolatie | Cross-tenant datalekken via SQL, missing tenant filters, tenant spoofing via X-Tenant header |
| API security          | CORS configuratie, input validatie gaps, rate limiting dekking                               |
| Data security         | Encryption at rest (credentials), SQL injection resistance, file upload sanitization         |
| Secrets management    | Env var handling, credential rotation, encryption key management                             |
| Logging & auditing    | Wat wordt gelogd, wat ontbreekt, audit trail completeness                                    |
| Infrastructure        | Docker exposure, Railway configuratie, MySQL port binding                                    |
| Compliance            | GDPR (EU data, tenant data isolation), financial data handling                               |
| **SAM edge (Lambda)** | Verified-JWT aan de edge, `X-Tenant` = select-niet-grant (ADR 0007), 403-gedrag bij mismatch, thin-handler (geen logic/DynamoDB in handler) |
| **SAM tenancy (DynamoDB)** | `tenant_id` PK + IAM `LeadingKeys` in de repository-laag, `sam-*` IAM-scope, geen cross-tenant lek via een handler die de repository omzeilt |
| **PreTokenGen Lambda** | Correctheid van de `custom:entitlements` mint (fail-safe omit vs fail-fast config), tenant_keys-scoping, kan een fout hier ELKE downstream authz misleiden |
| **SAM cross-account & deploy** | Account-scheiding (identity `personal` vs infra `nonprofit-deploy`), OIDC-deploy least-privilege, `samconfig.toml` niet-manipuleerbaar, geen inline stack overrides |
| **Plane-koppeling** | Import-/dependency-koppeling tussen Flask- en SAM-plane (bv. Flask-only code die in de Lambda-import-graph belandt), gedeelde `sam/shared` toolkit-integriteit |

### Geef per domein

- Huidige status (goed/matig/zwak)
- Gevonden risico's
- Concrete verbeteringen met codevoorbeelden
- Prioriteit (Critical/High/Medium/Low)

---

## 2. Red Team — Aanvalspaden

Gedraag je als een red-team security consultant die specifiek myAdmin aanvalt.

### Bekende aanvalsvectoren voor dit systeem

Onderzoek stap voor stap hoe een kwaadwillende gebruiker:

**Tenant-isolatie doorbreken:**

- De `X-Tenant` header manipuleren om data van een andere tenant op te vragen
- Een route vinden die `@tenant_required()` mist maar wel tenant-data retourneert
- Via de SysAdmin bypass (`allow_sysadmin=True`) ongeautoriseerde toegang verkrijgen
- SQL queries exploiteren waar de `administration` filter ontbreekt

**Privilege escalation:**

- JWT payload manipuleren om `cognito:groups` te wijzigen (aangezien er geen signature verification in de backend zit)
- Per-tenant role cache poisoning via timing attacks
- Van Finance_Read naar Finance_CRUD escaleren door directe API calls

**Data exfiltratie:**

- OpenRouter API responses manipuleren via prompt injection in factuur-PDFs
- Google Drive tokens stelen via credential service exploits
- Banking CSV import met malicious payloads (SQL injection via data velden)
- Bulk data export zonder rate limiting

**Business logic bypass:**

- Password reset code brute-forcing (6-digit, is dat voldoende entropy?)
- Trial plan expiry bypass door timestamp manipulatie
- Duplicate detection omzeilen voor dubbele transacties
- File upload filter bypass via double extensions of MIME type mismatch

**Infrastructure:**

- MySQL port 3306 exposed op host (Docker) — directe DB access
- Flask debug mode detection en exploitation
- Volume mount `/app/reports` pad traversal
- Environment variable leakage via error messages

**SAM / module plane (Lambda + DynamoDB):**

- **Tenant-selectie forceren:** een `X-Tenant` sturen die NIET in de geverifieerde `tenant_keys` zit — verwacht 403; test of een handler ooit "default-to-first" of fallback doet i.p.v. te weigeren (ADR 0007-bypass)
- **Repository omzeilen:** een handler of service vinden die DynamoDB direct benadert zonder de repository-laag → `tenant_id`/`LeadingKeys`-scoping wordt overgeslagen → cross-tenant read/write
- **DynamoDB query zonder tenant-scope:** een query/scan die niet op `tenant_id` als partition key beperkt is (bv. een table Scan of een GSI zonder tenant-conditie) → data van alle tenants
- **PreTokenGen misleiden:** de entitlement-mint beïnvloeden zodat een gebruiker `custom:entitlements`/`tenant_keys` krijgt voor een tenant die niet van hem is; of de fail-safe "omit" forceren zodat authz open faalt i.p.v. dicht
- **IAM-scope te ruim:** Lambda-execution-role die breder is dan `sam-*` / de eigen module-tabel, of `LeadingKeys` niet correct gebonden → laterale toegang tot andere modules/tenants
- **Cross-account verwarring:** de `.env` static keys (account `personal`) die `AWS_PROFILE=nonprofit-deploy` overschrijven, zodat een operatie stilletjes tegen het verkeerde account draait (zie `41-shell-environment.md`)
- **Plane-koppeling exploiteren:** Flask-only afhankelijkheden die in de Lambda-import-graph lekken (recent gezien: `flask` via `auth/__init__` → collapse), of een gedeelde `sam/shared`-helper compromitteren die door alle modules wordt vertrouwd
- **Deploy-keten:** de OIDC-deploy-workflow of `samconfig.toml` manipuleren om een kwaadaardige stack/parameters te deployen

### Voor elke aanval, beschrijf

1. Precondities (welke toegang heeft de aanvaller?)
2. Stap-voor-stap exploit
3. Impact (data breach, financial loss, service disruption)
4. Detectie (wordt deze aanval opgemerkt in huidige logging?)
5. Mitigatie (concrete fix met code)

---

## 3. Risk Manager — Beheer en Prioritering

Gedraag je als een security risk manager die het risicobeheer voor myAdmin opzet en onderhoudt.

### Context

myAdmin verwerkt:

- Financiële transacties en bankafschriften
- Facturen met AI-extractie
- BTW-aangiftes en inkomstenbelasting
- Short-term rental boekingen en inkomsten
- Multi-tenant data met strikte isolatie-eisen
- Google Drive documenten en credentials
- SAM-plane moduledata in DynamoDB (Members, straks Events/Webshop) met `tenant_id`-isolatie

### Opdracht

**A. Risicoregister opbouwen**

Maak een risicoregister in tabelformaat:

| #   | Risico | Categorie | Eigenaar | Impact (1-5) | Kans (1-5) | Score | Status | Mitigatie | Deadline |
| --- | ------ | --------- | -------- | ------------ | ---------- | ----- | ------ | --------- | -------- |

Categorieën: Authenticatie, Autorisatie, Data Integrity, Availability, Compliance, Supply Chain, Infrastructure

**B. Risicomatrix visualiseren**

Plaats de risico's in een 5x5 matrix (Impact × Kans) en identificeer:

- Rode zone (score ≥ 15): onmiddellijke actie vereist
- Oranje zone (score 8-14): gepland aanpakken
- Groene zone (score ≤ 7): accepteren of monitoren

**C. Mitigatieplan per kwartaal**

Stel een plan op met:

- Q1: Kritieke fixes (score ≥ 15)
- Q2: Hoge risico's (score 8-14)
- Q3: Medium risico's + hardening
- Q4: Audit, penetratietest, compliance check

**D. Continu risicobeheer**

Definieer:

- KPI's voor security health (bijv. % routes met tenant check, gemiddelde patch-tijd)
- Triggers voor her-assessment (nieuwe module, dependency update, incident)
- Escalatiepad bij security incident
- Verantwoordelijkheden (wie doet wat)

**E. Specifieke aandachtspunten voor myAdmin**

Analyseer deze bekende architecturale kenmerken op risico:

1. **JWT zonder signature verification in backend** — tokens worden base64-decoded maar niet cryptografisch geverifieerd tegen Cognito JWKS
2. **In-memory role cache** — geen distributed invalidation, 5 min window voor stale permissions
3. **OpenRouter API** — externe AI verwerkt potentieel gevoelige factuurdata
4. **Google Drive credentials in MySQL** — encrypted, maar single encryption key voor alle tenants
5. **MySQL port exposed in Docker** — development convenience vs security
6. **Security middleware disabled in debug/test mode** — risico als productie per ongeluk in debug draait
7. **CORS met wildcard origin** — `Access-Control-Allow-Origin: *` in sommige responses
8. **File uploads tot 100MB** — DoS vector zonder per-user rate limiting
9. **Password reset 6-digit code** — 1M mogelijkheden, 3 attempts = veilig, maar timing attacks?
10. **Terraform state file in repo** — bevat potentieel gevoelige infrastructure details

**SAM / module plane (Plane 2) — aparte aandachtspunten:**

11. **PreTokenGen Lambda als single point of authz-truth** — mint `custom:entitlements`; een bug (verkeerde `tenant_keys`, of fail-safe die open i.p.v. dicht faalt) misleidt ELKE downstream module-authz
12. **DynamoDB tenant-scoping in één laag** — `tenant_id` PK + IAM `LeadingKeys` leeft alleen in de repository; een handler/service die de repository omzeilt lekt cross-tenant. Meet: % module-datatoegang dat via de repository loopt
13. **`X-Tenant` = select-niet-grant (ADR 0007)** — de edge moet 403'en bij een tenant buiten `tenant_keys`; geen default-to-first/fallback
14. **IAM least-privilege voor Lambda-roles** — scope naar `sam-*` / eigen tabel; te ruime rollen = laterale beweging
15. **Cross-account boundary** — identity (`personal` 344561557829) vs infra/data (`nonprofit-deploy` 506221081911); `.env` static keys kunnen `AWS_PROFILE` overschrijven en ops tegen het verkeerde account draaien
16. **Plane-koppeling** — Flask-only code die in de Flask-vrije Lambda-import-graph belandt (bv. `flask` via `auth/__init__`), en de integriteit van de gedeelde `sam/shared` toolkit die alle modules vertrouwen
17. **SAM deploy-keten** — OIDC-workflow + committed `samconfig.toml`; geen hand-getypte overrides; supply-chain van de vendored Lambda-layer (o.a. `boto3`/`PyJWT`/`cryptography` pins)

### Gewenst resultaat

Een actionable risicobeheerplan dat:

- Prioriteert op basis van impact × kans
- Concrete taken bevat met tijdsinschatting
- Past bij een klein team (1-2 developers)
- Kwartaal-cadans volgt
- Meetbaar is (KPI's)

---

## Output — wat een security-run oplevert

Een run levert een **duurzame, dated spec** op (niet alleen chat-analyse), consistent met de andere prompts in deze map en met de bestaande security-home
`.kiro/specs/Common/Security/`. Maak:

```
.kiro/specs/Common/Security/security-assessment-YYYY-MM-DD/
├── .config.kiro        {"specId":"<uuid>","workflowType":"requirements-first","specType":"bugfix"}
├── tasks.meta.json     {"pbtResults":{},"executionHistory":{}}
├── requirements.md     de bevindingen (analyse)
└── tasks.md            de mitigatie-taken (actie)
```

**requirements.md** — de gecombineerde bevindingen, met tellingen en severity
(Critical/High/Medium/Low), **over BEIDE planes** (Flask/MySQL én SAM/DynamoDB),
expliciet gelabeld per plane zodat niets tussen wal en schip valt:

- **Security Architect** (perspectief 1): per domein status (goed/matig/zwak) + gevonden risico's + concrete fix met codevoorbeeld + prioriteit. Neem de SAM-domeinen mee (edge, DynamoDB-tenancy, PreTokenGen, cross-account/deploy, plane-koppeling).
- **Red Team** (perspectief 2): per aanvalspad preconditie → exploit-stappen → impact → detecteerbaarheid → mitigatie. Inclusief de SAM-aanvalspaden.
- **Risk Manager** (perspectief 3): het risicoregister (Impact×Kans, score, status), de 5×5-matrix (rood/oranje/groen), en de aandachtspunten E1–E17 (incl. de SAM-items 11–17).
- Tellingen: N Critical / N High / N Medium / N Low, per plane.

**tasks.md** — actionable mitigatie-taken gegroepeerd op prioriteit (rode zone score ≥ 15 eerst).
Elke taak: bestandspad(en), concrete actie, effort (S ≤ 30 min / M ≤ 2 h / L > 2 h), en een
verificatie-notitie. Beveiligingsgevoelige wijzigingen (auth, IAM, tenant-scoping) MOETEN
vermelden wat wél en niet lokaal te verifiëren is.

**Vergelijk met de vorige run:** kijk of er al een eerdere
`security-assessment-YYYY-MM-DD/` of `security-hardening/` in `.kiro/specs/Common/Security/`
staat. Zo ja: gaan de counts omlaag, welke risico's keren terug, welke zijn nieuw? Voeg een
"Lessons / Recurring Issues"-sectie toe.

> **Alleen analyse + spec — nog niet fixen.** Deze run produceert de assessment en de
> takenlijst. Voer de mitigaties uit als een aparte stap (waarbij de Change-With-Tests
> Contract geldt voor elke gedragswijziging).

## Gebruik

### Optie A: Volledige assessment

Voer alle drie prompts uit en combineer de resultaten tot één security roadmap.

### Optie B: Snelle scan

Gebruik alleen prompt 2 (Red Team) voor de meest urgente kwetsbaarheden.

### Optie C: Periodieke review

Gebruik prompt 3 (Risk Manager) elk kwartaal om de voortgang te meten.

### Tips voor maximale effectiviteit

- Geef de AI toegang tot de relevante bronbestanden:
  - **Flask-plane:** `backend/src/auth/`, `backend/src/routes/`, `backend/src/database.py`, `docker-compose.yml`
  - **SAM-plane:** `sam/shared/` (auth/entitlement toolkit), `sam/pretokengen/` (token-mint Lambda), `sam/<module>/handler/` + `sam/<module>/repository/` + `sam/<module>/domain/` (bv. `sam/members/`), `samconfig.toml`, de deploy-workflows
- Verwijs naar de steering files voor architectuur-context (`.kiro/steering/`), i.h.b. `20-platform-architecture.md` (two-plane), `35-sam-module-architecture-sam.md`, `22-authentication.md` (verified-JWT), `23-aws-accounts.md` (cross-account) en ADR `docs/decisions/0007-active-tenant-resolution-sam-edge.md`
- Specificeer welke plane en omgeving: Flask (Docker dev / Railway prod) of SAM (`nonprofit-deploy` AWS, per-env stacks)
- Vraag om concrete code-patches, niet alleen adviezen
