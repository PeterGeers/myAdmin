# theory7 — connect www.thecategorystudio.nl to myAdmin

One-time DNS change at theory7 (the DNS host of `thecategorystudio.nl`). Everything on the
myAdmin / AWS side is already in place; this is the only manual step.

| | |
|---|---|
| Domain | `www.thecategorystudio.nl` |
| myAdmin tenant / slug | `kimgeers` / `thecategorystudio` |
| CNAME target | `d3cae492lrd6sc.cloudfront.net` |
| Status in myAdmin now | `pending_dns` (waiting for this change) |
| Time needed | ~10 minutes of work, then up to a few hours of waiting |

---

## 1. Before you start

1. **Agree it with the tenant.** As soon as the record is active, `www.thecategorystudio.nl`
   shows the myAdmin landing page. Whatever theory7 currently serves on `www`
   (`213.154.231.202`) is no longer visible there.
2. **The bare domain is not affected.** `thecategorystudio.nl` (without `www`) keeps working
   as it does today. Do not change records for `@` / the bare domain.
3. **Email is not affected.** Do not touch MX, TXT (SPF/DKIM/DMARC) or any other record.

## 2. Open the DNS records

1. Log in at **my.theory7.net**.
2. Open **DirectAdmin** for `thecategorystudio.nl`.
3. Go to **DNS Management** (*DNS Zone Editor* / *DNS beheer*) and select
   `thecategorystudio.nl`.
4. **Make a backup:** take a screenshot of the full record list, or write down every record
   whose name is `www`. You need this to undo the change.

## 3. Remove the current `www` records

`www` currently has an **A** record and an **AAAA** record (checked 15 Nov 2026). A name with
a CNAME may not have any other record, so both must go:

| Delete | Name | Type | Value |
|---|---|---|---|
| ✗ | `www` | A | `213.154.231.202` |
| ✗ | `www` | AAAA | `2001:7b8:618:a:213:154:231:202` |

For each: find the row → **Delete** (trash icon) → confirm.
If you find another `www` record (for example a CNAME to `thecategorystudio.nl.`), delete that
too. Leave every other row alone.

## 4. Add the new CNAME

Click **Add Record** and enter:

| Field | Value |
|---|---|
| Type | `CNAME` |
| Name | `www` |
| Value | `d3cae492lrd6sc.cloudfront.net.` |
| TTL | leave the default (or `3600`) |

Note the **trailing dot** after `.net.` — DirectAdmin needs it. Without it the panel appends
the domain and the record becomes `d3cae492lrd6sc.cloudfront.net.thecategorystudio.nl`, which
does not work.

Click **Add**. The list should now show exactly one `www` row: the CNAME.

## 5. Check that the record is visible

Usually within minutes to 1–2 hours (worst case 48 hours).

- **Online:** go to **dnschecker.org**, enter `www.thecategorystudio.nl`, choose type **CNAME**.
  Most locations should show `d3cae492lrd6sc.cloudfront.net`.
- **Command line** (optional): `nslookup -type=CNAME www.thecategorystudio.nl`

## 6. Activate in myAdmin

1. Log in to myAdmin as tenant `kimgeers` → Landing page → **Eigen Domein**.
2. Click **Controleren**. (A background check does the same automatically, so this is only to
   speed things up.)
3. Expected progression:
   - *pending_dns* — record not visible to CloudFront yet → wait and try again later.
   - *validating* — CloudFront sees the record and is issuing the certificate (≤ 30 minutes).
   - *active* — done.
4. Open **https://www.thecategorystudio.nl** — it shows the thecategorystudio landing page with
   a valid padlock.

## 7. Undo (if needed)

1. In DNS Management, delete the `www` CNAME.
2. Re-add the records from your backup:
   - `www` A `213.154.231.202`
   - `www` AAAA `2001:7b8:618:a:213:154:231:202`
3. Optionally remove the domain in myAdmin → Eigen Domein → **Domein verwijderen**.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Panel refuses the CNAME ("record already exists" / conflict) | An A, AAAA or other `www` record is still there. Delete it (step 3) and add the CNAME again. |
| dnschecker shows `…cloudfront.net.thecategorystudio.nl` | Trailing dot was missing. Edit the record and set the value to `d3cae492lrd6sc.cloudfront.net.` |
| dnschecker still shows `213.154.231.202` | Old record still cached. Wait (up to the old TTL), then check again. |
| myAdmin stays on *pending_dns* for hours although dnschecker is correct | Click **Controleren** again. If it persists, ask the developer to check the Railway logs for `distribution tenant` errors. |
| Status *failed* | The certificate could not be validated (e.g. DNS changed back). Fix DNS, then in Eigen Domein remove the domain and register `www.thecategorystudio.nl` again. |
| Browser shows a certificate warning | The certificate is not issued yet. Wait until myAdmin shows *active*. |
| Email stops working | An MX/TXT record was changed by accident. Restore it from your backup — this change never needs them. |

## Background (for the developer)

- Custom domains are served by the CloudFront multi-tenant distribution `ET9HYEGAY09WF`
  (nonprofit account `506221081911`); each domain is a distribution tenant with origin path
  `/{slug}` and a CloudFront-managed, HTTP-validated certificate.
- CloudFront only creates the tenant once this CNAME points at the connection-group endpoint;
  `verify` / the background job (`check_custom_domain`) retry until then.
- Only `www` is supported: a bare domain needs an ALIAS record, which DirectAdmin does not offer.
- Spec: `tasks.md` → task C.
