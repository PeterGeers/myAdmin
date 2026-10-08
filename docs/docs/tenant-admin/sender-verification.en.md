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
