# Sender verification

> Add and verify a sender email address, so your tenant can mail from an address you control.

## Overview

Before your organization can send mail from myAdmin (for example the member mailings and deliveries from [Member Administration](../members/delivery.md)), you as Tenant Admin must add and **verify** a **sender address** once. Only when a sender is verified and your tenant is **cleared to send** do the mail actions appear for your users.

!!! info
The mail actions in the modules (such as **Mail**, a delivery, and scheduling in Member Administration) are **hidden** as long as your tenant is not cleared. Once the clearance is in place, they appear on their own.

## Adding and verifying a sender

1. In **Tenant Admin**, go to the **Senders** section (sender verification).
2. Enter the **sender email address** you want to use (an address your organization controls).
3. Confirm; the system starts verification and sends a **verification email** to that address.
4. Open that email and follow the confirmation link.
5. Back in the list, the **status** of the address changes to *verified*.

!!! info
Verification confirms that your organization actually controls the address. This is a one-time step per sender address.

!!! tip
Use an address your team can actually receive (for example a shared mailbox), so you can open the confirmation link. A no-reply address without a mailbox cannot receive the verification email.

## The clearance to mail (mail-enabled)

Besides a verified sender, a per-tenant **clearance to send** applies. This clearance decides whether the mail actions are offered for your tenant:

- If your tenant is **not** cleared, your users do not see the mail actions.
- If your tenant **is** cleared and there is a verified sender, users can mail, configure a delivery, and (with enough permissions) schedule.

!!! info
The clearance and the verified sender belong together: the sent mail goes out from your verified sender address.

## Sender status

In the list you see the status per sender:

| Status   | Meaning                                                              |
| -------- | ------------------------------------------------------------------- |
| Pending  | The verification email was sent; the confirmation link has not been followed yet |
| Verified | The address is confirmed and can be used as a sender                |

## Permissions

| Permission     | What the user can do                                     |
| -------------- | -------------------------------------------------------- |
| `Tenant_Admin` | Add and verify sender addresses for the tenant           |

!!! info
Sender verification is reserved for the **Tenant Admin**. Regular users cannot add senders; they only see the mail actions once the tenant is cleared.

## Troubleshooting

| Problem                              | Cause                                               | Solution                                                      |
| ------------------------------------ | --------------------------------------------------- | ------------------------------------------------------------- |
| Verification email not received      | Wrong address, or the mail is in spam               | Check the address and the spam folder; re-add the address if needed |
| Status stays *Pending*               | The confirmation link has not been followed yet     | Open the verification email and follow the link              |
| Users see no mail actions            | No verified sender, or tenant not cleared           | Verify a sender; the actions appear after clearance          |
| Mail does not reach recipients       | The sender is not yet verified                      | Finish verification before you send                          |

---

## Runbook: getting your mail domain certified (onboarding)

> This section describes the **onboarding process** by which your tenant is cleared to mail from your **own domain** (for example `noreply@yourclub.org`). This is a **guided, one-time** process — not a self-service button in the application. You do it together with the platform operator; you add the DNS records, the operator does the mail-service side and records the certification.

!!! info
The difference from [adding a sender](#adding-and-verifying-a-sender) above: there you verify a single **address**; here you certify a whole **domain**. With a certified domain, Member Administration sends from `noreply@<your-domain>` — a fixed, generic per-tenant sender address.

### The sender you get

Once your domain is certified, every member mail goes out from:

- **From:** `noreply@<your-domain>` — a fixed, generic address per tenant (not configurable per user).
- **Reply-To:** the email address of the logged-in user sending the mail, so replies reach the right person.

!!! info
The local part (`noreply`) is fixed by default. A different local part (for example `info`) is only possible if that was agreed and recorded during onboarding.

### Step 1 — What you supply

Provide the operator with:

1. The **mail domain** you want to use (for example `yourclub.org`). It must be a domain you control and whose **DNS you can change**.
2. Optionally a different sender **local part** (default `noreply`).

### Step 2 — The operator creates the domain identity

The operator registers your domain as a **sending identity** with the mail service (SES). That produces a set of **DNS records** for you to add to your domain — this is what proves you actually control the domain.

### Step 3 — Add the DNS records (your side)

At your domain registrar (or DNS manager), add the records the operator gives you:

| Record            | Purpose                                                                                  |
| ----------------- | ---------------------------------------------------------------------------------------- |
| **DKIM** (3× CNAME) | Signs your outgoing mail so recipients can verify it genuinely comes from your domain. The mail service usually provides **three** CNAME records. |
| **SPF** (TXT)     | States which servers may send on behalf of your domain. Add the `include` the operator provides to your existing SPF record (do not add a second SPF record). |
| **MAIL FROM** (optional, MX + TXT) | Only if the operator sets up a custom "MAIL FROM" subdomain; then add those records too. |

!!! warning
Do **not** add a second SPF record. A domain should have exactly one SPF TXT record; if one already exists, extend it with the supplied `include` rather than adding a new one. Two SPF records actually make your mail less trustworthy.

!!! tip
DNS changes can take a while to become visible everywhere (from a few minutes to sometimes hours). Be patient before you treat verification as failed.

### Step 4 — Confirm the domain is verified

Once the DNS records are live, the mail service checks them automatically. The operator confirms that the domain identity has the **verified-for-sending** status (`VerifiedForSendingStatus`). Only then is the domain usable as a sender.

!!! info
Besides domain verification, the account-wide precondition applies that sending is enabled (out of the "sandbox"). The operator watches that as an operational condition; it is not a step you do per send.

### Step 5 — Record the certification (`mail_certified`)

Finally, the operator records the certification as **tenant parameters**:

| Parameter          | Value / meaning                                                          |
| ------------------ | ------------------------------------------------------------------------ |
| `mail_domain`      | Your certified domain (for example `yourclub.org`)                       |
| `mail_local_part`  | The sender's local part; default `noreply`                               |
| `mail_certified`   | `true` once the domain is verified — this is the switch the send relies on |
| `mail_enabled`     | `true` to clear the mail actions for the tenant                          |

These parameters are entered during onboarding and **projected** to the sending environment, just like the other tenant settings. The send reads `mail_certified` right before sending: if it is not `true`, nothing is sent.

!!! warning
`mail_certified` is a **recorded** state, not a live measurement. If the domain's certification lapses later (for example because DNS records are removed), the certification must be re-checked and re-recorded. So do not remove the DKIM/SPF records while you keep mailing.

### If your tenant is not (yet) certified

As long as `mail_certified` is not `true`, the **fail-closed** rule applies:

- The send is **not** carried out. There is **no** substitute sender — never a foreign or platform domain.
- The user gets a clear, actionable message: *"your tenant's mail is not certified — contact your administrator."*

!!! info
This is deliberate: better a clear block with an action than a silent failure or a mail that goes out from the wrong domain. See also [Sending & delivery](../members/delivery.md) and [Mail status](../members/mail-status.md).

!!! info
This certification belongs with your **tenant information**. See [Settings](tenant-settings.md) for the other tenant settings; the mail domain and the certification are entered during onboarding and stored with your tenant.
