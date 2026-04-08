# Changelog

> Overview of changes per version.

## April 2026

### New

- **Documentation site** — Full user documentation available at `/docs/` and via in-app help
- **Bilingual** — Documentation available in Dutch and English
- **In-app help** — Help icon on every page opens relevant documentation

### Improvements

- **Email system** — All emails (invitations, password resets, tenant additions) now go through one system (SES) and are tracked in the email log
- **Password reset** — Reset emails now come from `support@jabaki.nl` instead of `no-reply@verificationemail.com`
- **User deletion** — Improved safety: users with access to multiple tenants are no longer accidentally fully deleted
- **Resend invitation** — If the email cannot be sent, the temporary password is displayed for manual sharing
- Initial release of user documentation

---

_Previous changes will be added here with future releases._
