"""Best-effort provisioning notification emails for tenant-admin user routes.

Extracted from ``routes.tenant_admin_users`` (task 15 split) so that module stays
focused on request handling. Both helpers are intentionally swallowing — a failed
email must never fail user provisioning, matching the original inline
``try/except`` blocks — and keep the exact AUDIT/WARNING log lines.

``email_service`` / ``invitation_service`` are constructed by the caller so the
existing patch points (``routes.tenant_admin_users.EmailTemplateService`` /
``.InvitationService``) and the caller-provided mocks keep working. SES and the
frontend-URL helper are imported lazily so ``services.ses_email_service`` /
``utils.frontend_url`` stay patchable at call time.
"""


def send_tenant_added_notification(*, tenant, email, user_email, user_response) -> None:
    """Email an existing user that they were added to ``tenant`` (never raises)."""
    try:
        from services.email_template_service import EmailTemplateService
        from services.ses_email_service import SESEmailService
        from utils.frontend_url import get_frontend_url

        email_service = EmailTemplateService(administration=tenant)
        ses = SESEmailService()
        login_url = get_frontend_url()

        # Get user's display name
        user_name = email.split("@")[0]
        for attr in user_response.get("UserAttributes", []):
            if attr["Name"] == "name":
                user_name = attr["Value"]
                break

        html_content = email_service.render_template(
            template_name="tenant_added",
            variables={
                "email": email,
                "tenant": tenant,
                "name": user_name,
                "login_url": login_url,
            },
            format="html",
        )

        text_content = (
            f"Hi {user_name},\n\n"
            f"You have been added to the {tenant} tenant in myAdmin.\n\n"
            f"You can log in with your existing credentials at: {login_url}\n\n"
            f"Regards,\nmyAdmin"
        )

        subject = f"You've been added to {tenant} in myAdmin"

        result = ses.send_invitation(
            to_email=email,
            subject=subject,
            html_body=html_content or text_content,
            text_body=text_content,
            administration=tenant,
            sent_by=user_email,
        )

        if result["success"]:
            print(
                f"AUDIT: Tenant-added notification sent to {email} for tenant {tenant}",
                flush=True,
            )
        else:
            print(
                f"WARNING: Failed to send tenant-added notification to {email}: {result.get('error')}",
                flush=True,
            )

    except Exception as e:
        # Don't fail the operation if email fails
        print(
            f"WARNING: Failed to send tenant-added notification to {email}: {e}",
            flush=True,
        )


def send_new_user_invitation(
    *, tenant, email, user_email, temp_password, email_service, invitation_service
) -> None:
    """Email a freshly-created user their invitation (never raises)."""
    try:
        # Render email templates using render_user_invitation which detects language
        from utils.frontend_url import get_frontend_url

        login_url = get_frontend_url()

        html_content = email_service.render_user_invitation(
            email=email,
            temporary_password=temp_password,
            tenant=tenant,
            login_url=login_url,
            format="html",
        )

        text_content = email_service.render_user_invitation(
            email=email,
            temporary_password=temp_password,
            tenant=tenant,
            login_url=login_url,
            format="txt",
        )

        # Send via SES (direct to recipient)
        from services.ses_email_service import SESEmailService

        ses = SESEmailService()
        # Get subject with detected language
        subject = email_service.get_invitation_subject(
            tenant, language=email_service._detect_user_language(email, tenant)
        )

        result = ses.send_invitation(
            to_email=email,
            subject=subject,
            html_body=html_content,
            text_body=text_content
            or f"Welcome to {tenant}! Your temporary password: {temp_password}",
            administration=tenant,
            sent_by=user_email,
        )

        if result["success"]:
            # Mark invitation as sent
            invitation_service.mark_invitation_sent(administration=tenant, email=email)
            print(
                f"AUDIT: Invitation email sent to {email} by {user_email} for tenant {tenant}",
                flush=True,
            )
        else:
            print(
                f"WARNING: SES failed to send invitation to {email}: {result.get('error')}",
                flush=True,
            )
            invitation_service.mark_invitation_failed(
                administration=tenant,
                email=email,
                error_message=f"SES send failed: {result.get('error')}",
            )

    except Exception as e:
        # Don't fail user creation if email fails, but log it
        print(
            f"WARNING: Failed to send invitation email to {email}: {e}",
            flush=True,
        )
        invitation_service.mark_invitation_failed(
            administration=tenant,
            email=email,
            error_message=f"Email send failed: {e!s}",
        )
