# Security Assessment Prompts — myAdmin

Drie perspectieven voor een grondige security-analyse van myAdmin:

1. Security Architect (beoordeling)
2. Red Team (aanvalspaden)
3. Risk Manager (beheer en prioritering)

---

## 1. Security Architect — Beoordeling

Analyseer de security-architectuur van myAdmin alsof je een senior security architect bent.

### Architectuur-context

myAdmin is een multi-tenant SaaS-platform voor financiële administratie en short-term rental beheer.

**Stack:**

- Backend: Python Flask + Waitress, MySQL 8.0, Docker
- Frontend: React 19 + TypeScript, Vite
- Auth: AWS Cognito (JWT), per-tenant RBAC via `cognito_required` + `tenant_required` decorators
- Externe APIs: OpenRouter AI (factuurextractie), Google Drive (opslag), AWS SNS (notificaties), AWS SES (e-mail)
- Infra: Docker Compose (dev), Railway (productie), Terraform (AWS resources)
- Credentials: Fernet-encrypted in MySQL, master key via `CREDENTIALS_ENCRYPTION_KEY` env var

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

### Gewenst resultaat

Een actionable risicobeheerplan dat:

- Prioriteert op basis van impact × kans
- Concrete taken bevat met tijdsinschatting
- Past bij een klein team (1-2 developers)
- Kwartaal-cadans volgt
- Meetbaar is (KPI's)

---

## Gebruik

### Optie A: Volledige assessment

Voer alle drie prompts uit en combineer de resultaten tot één security roadmap.

### Optie B: Snelle scan

Gebruik alleen prompt 2 (Red Team) voor de meest urgente kwetsbaarheden.

### Optie C: Periodieke review

Gebruik prompt 3 (Risk Manager) elk kwartaal om de voortgang te meten.

### Tips voor maximale effectiviteit

- Geef de AI toegang tot de relevante bronbestanden (auth/, routes/, database.py, docker-compose.yml)
- Verwijs naar de steering files voor architectuur-context (.kiro/steering/)
- Specificeer of je de assessment wilt voor development (Docker) of production (Railway)
- Vraag om concrete code-patches, niet alleen adviezen
