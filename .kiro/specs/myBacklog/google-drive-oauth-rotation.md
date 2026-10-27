# Google Drive OAuth — rotation / reconfiguration follow-up

> Backlog item. Surfaced while rotating tenant Google Drive credentials during the Railway-breach
> response (`.kiro/specs/Common/Security/railway-breach-rotation/` Task 13). The breach rotation
> itself is complete; this is a Google OAuth *configuration* fix that must be done against the
> Google Cloud Console + the myAdmin Storage UI (not scriptable from the repo).

## Symptom

After uploading a new Google OAuth client secret and re-authorizing, the Drive connection test fails:

```
Connection failed
Token expired and refresh failed: ('invalid_client: The provided client secret is invalid.',
  {'error': 'invalid_client', 'error_description': 'The provided client secret is invalid.'})
```

The OAuth consent screen completes ("successful"), but the subsequent **server-side token
refresh** is rejected by Google.

## Root cause (diagnosed 2026-10-23)

`invalid_client` on refresh = Google rejects the `client_id`+`client_secret` pair the backend sends.
The backend reads that pair from the stored `google_drive_credentials` (per tenant) — see
`backend/src/routes/tenant_admin_credentials.py` `start_oauth_flow` (reads
`google_drive_credentials`) and `backend/src/services/google_oauth_service.py` (token exchange /
refresh). Two concrete misconfigurations found:

1. **Wrong OAuth client TYPE.** The uploaded file
   (`client_secret_2_867173990423-...apps.googleusercontent.com.json`) is a **Desktop ("installed")**
   client: `"installed"` block, `redirect_uris: ["http://localhost"]`. myAdmin performs a
   **web server-side** authorization-code + refresh flow, which requires a **Web application** OAuth
   client. A Desktop client's secret does not work for the server-side refresh → `invalid_client`.

2. **`GOOGLE_REDIRECT_URI` is NOT set in Railway** (prod). The backend therefore defaults to
   `http://localhost:5000/api/tenant-admin/credentials/oauth/callback`
   (`google_oauth_service.py` and `tenant_admin_credentials.py`). In production the redirect URI must
   be the real backend callback URL AND must exactly match an Authorized redirect URI registered on
   the OAuth client. A mismatch breaks the exchange/refresh.

3. **Possible multiple clients.** The filename `client_secret_2_...` suggests more than one OAuth
   client in project `handle-files-in-facturen`. The stored secret and the token MUST come from the
   SAME Web client.

## Environment facts gathered

- **CONFIRMED backend public URL = `https://invigorating-celebration-production.up.railway.app`**
  (`/api/health` → 200, `/api/tenant-admin/credentials/oauth/callback` → 400 = route exists). This is the
  Railway SERVICE domain (port 8080).
- ⚠️ The custom domain `pgeers.nl` (also on the service, port 5000) does NOT cleanly serve the API — `pgeers.nl/`
  301-redirects to a **Google Sites** page (`sites.google.com/pgeers.nl/mytrips/...`) and `pgeers.nl/api/health`
  → 404. So do NOT use `pgeers.nl` for the OAuth redirect URI; use the railway.app service domain.
- `FRONTEND_URL` = `https://petergeers.github.io/myAdmin`; `VITE_API_URL` (local) = `http://localhost:5000`.
- Google project: `handle-files-in-facturen`.
- **THE redirect URI to register + set as `GOOGLE_REDIRECT_URI`:**
  `https://invigorating-celebration-production.up.railway.app/api/tenant-admin/credentials/oauth/callback`
- Credential storage: encrypted rows `google_drive_credentials` / `google_drive_oauth` /
  `google_drive_token` per tenant (GoodwinSolutions, PeterPrive). Re-encrypted under the NEW
  `CREDENTIALS_ENCRYPTION_KEY` during the breach rotation (Task 8) — decryption works in the live app.

## Fix (to do against Google Console + myAdmin Storage UI)

1. **Confirm the exact production backend base URL** that serves `/api/...` (is it `https://pgeers.nl`?).
   The OAuth redirect URI must point at that host's
   `/api/tenant-admin/credentials/oauth/callback`.
2. **Google Cloud Console** (`https://console.cloud.google.com/apis/credentials`, project
   `handle-files-in-facturen`): create an **OAuth client ID → Application type: Web application**.
   Add Authorized redirect URI:
   `https://<backend-host>/api/tenant-admin/credentials/oauth/callback`
   (e.g. `https://pgeers.nl/api/tenant-admin/credentials/oauth/callback` once confirmed).
   Download this Web client's JSON. Remove/avoid the Desktop client.
3. **Set `GOOGLE_REDIRECT_URI` in Railway** (app service) to the EXACT same URL:
   `~/.railway/bin/railway variable set GOOGLE_REDIRECT_URI="https://<backend-host>/api/tenant-admin/credentials/oauth/callback" --service invigorating-celebration`
   (triggers a redeploy).
4. **Upload the new WEB client JSON** per tenant via Tenant Admin → Storage (the place the Drive
   client config is managed). Ensure it lands as `google_drive_credentials`.
5. **Re-authorize** (Start Google Drive OAuth) per tenant → the new `google_drive_token` is issued
   against the Web client and stored. Then **Test Google Drive Connection** → should pass.
6. Verify a real Drive action per tenant (e.g. listing subfolders).

## Security note

The breach-exposed Google tokens are addressed by: (a) the decryption PATH is already closed
(`CREDENTIALS_ENCRYPTION_KEY` + DB password rotated), and (b) once the Web client re-auth succeeds,
the new tokens replace the old ones. If you want to kill the OLD tokens immediately regardless of
the reconfig, revoke myAdmin's access at `https://myaccount.google.com/permissions` for the Google
account that authorized Drive — that invalidates the leaked refresh tokens now.

---
*Diagnosed 2026-10-23 during the Railway-breach rotation. Not a breach-rotation blocker — the
breach secrets are all rotated; this is a Google OAuth client-type + redirect-URI config fix.*

---

## RESOLVED 2026-10-23 — actual root cause + the real fix

The `invalid_client` / `redirect_uri_mismatch` ordeal (8+ hours, multiple new OAuth clients) had ONE
underlying cause, and it was NOT Google propagation:

**The Storage UI uploads a Google client file under credential_type `google_drive`, but the OAuth
flow (`start_oauth_flow` in `backend/src/routes/tenant_admin_credentials.py`) reads
`google_drive_credentials`.** So every new client file the user uploaded landed in the WRONG slot
and was ignored by the OAuth flow, which kept using the STALE OLD `google_drive_credentials` →
old client_id → redirect URI didn't match the registered one → `redirect_uri_mismatch`. Creating
more clients / waiting for propagation could never fix it.

**Fix applied (manual, this incident):** copied the fresh `google_drive` encrypted_value into the
`google_drive_credentials` row (verbatim ciphertext copy — same per-tenant Fernet salt, so no
decrypt needed) for both tenants via `railway-db.sh`. Then "Start Google Drive OAuth" → consent →
fresh token → Test PASSED. Drive restored.

Evidence trail that pinned it: the Tenant-Admin credentials list showed `google_drive` updated
2026-10-23 (new) while `google_drive_credentials`/`_oauth`/`_token` were still 2026-10-22 22:52 (old);
the failing authorize URL carried the NEW client_id only AFTER the slot copy.

## Backlog fixes to make (so this never recurs)

1. **Fix the credential-type mismatch (root cause).** Either:
   - make the Storage/Credentials upload store the Google OAuth *client* file under
     `google_drive_credentials` (the type the OAuth flow reads), with a clear dropdown option; AND/OR
   - make `start_oauth_flow` fall back to the `google_drive` type when `google_drive_credentials`
     is absent/older. Pick one canonical type and make upload + read agree.
   - The upload modal dropdown currently offers only `google_drive` (Service Account) / S3 / Azure —
     it has NO `google_drive_credentials` (OAuth client) option. Add one, or relabel.

2. **Surface the failure detail (user's request — would have saved HOURS).** When the Drive
   connection test / token refresh fails, the UI shows a generic "Connection failed". Capture and
   DISPLAY (or log to a viewable place) the actionable detail WITHOUT leaking secrets:
   - the Google error `error` + `error_description` (e.g. `invalid_client`, `redirect_uri_mismatch`),
   - the `client_id` being used (semi-public — safe to show),
   - the `redirect_uri` being sent vs. expected,
   - which credential_type/slot the flow read.
   A small "diagnostics" panel or a token-health detail on the Credentials tab. Do NOT print the
   client_secret or tokens. This turns an opaque multi-hour mystery into a self-serve fix.

3. **Set `GOOGLE_REDIRECT_URI` as managed config** (it was unset → defaulted to localhost). It is now
   `https://invigorating-celebration-production.up.railway.app/api/tenant-admin/credentials/oauth/callback`
   in Railway. Consider documenting it as a required prod var so a fresh deploy can't regress to the
   localhost default.

## Key facts (confirmed)

- Backend public URL serving `/api/...`: `https://invigorating-celebration-production.up.railway.app`
  (NOT `pgeers.nl`, which redirects to a Google Site).
- OAuth redirect URI (registered on the Web client AND set as `GOOGLE_REDIRECT_URI`):
  `https://invigorating-celebration-production.up.railway.app/api/tenant-admin/credentials/oauth/callback`
- OAuth client must be **Web application** type (not Desktop/"installed").
- The PR #164 URL-encoding fix (merged to main) was also needed — the authorize URL wasn't
  percent-encoding `redirect_uri`; that fixed the FIRST `redirect_uri_mismatch` layer; the slot
  mismatch was the SECOND, deeper layer.
