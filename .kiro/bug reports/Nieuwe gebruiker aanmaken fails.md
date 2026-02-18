Nieuwe gebruiker aanmaken

E-mail*
pjageers@gmail.com
Weergavenaam
PJA
Tijdelijk wachtwoord*
••••••••••••••
Rollen

E-mail is verzonden maar in het engels

## Status

**FIXED AND VERIFIED** - Email now correctly sent in Dutch based on tenant's default_language setting.

## Issue Analysis

1. **User Creation**: ✅ Working correctly
2. **Email Sending**: ✅ Working correctly in Dutch
3. **Timeout Issue**: ✅ Resolved with 30-second timeout + graceful error handling
4. **Language Detection**: ✅ Now properly detects tenant's default_language from database

## Root Cause

The user creation endpoint was calling `render_template()` directly instead of using `render_user_invitation()`, which bypassed the language detection logic.

## Solution Applied

Changed from manual `render_template()` calls to `render_user_invitation()` method:

**Before** (bypassed language detection):

```python
html_content = email_service.render_template(
    template_name='user_invitation',
    variables={...},
    format='html'
    # No language parameter - used default
)
```

**After** (proper language detection):

```python
html_content = email_service.render_user_invitation(
    email=email,
    temporary_password=temp_password,
    tenant=tenant,
    login_url=...,
    format='html'
    # Automatically detects language from tenant
)
```

## Language Detection Priority (Now Working)

1. ✅ User's `custom:preferred_language` attribute in Cognito (if set)
2. ✅ Tenant's `default_language` from database (GoodwinSolutions = 'nl')
3. ✅ Default to 'nl' (Dutch)

## Verification

- Created user for GoodwinSolutions tenant
- Email received in Dutch (using `user_invitation_nl.html` template)
- Subject line: "Welkom bij myAdmin - GoodwinSolutions Uitnodiging"
- All content properly translated

## Files Modified

- `backend/src/services/email_template_service.py` - Fixed default language to 'nl'
- `backend/src/routes/tenant_admin_users.py` - Use render_user_invitation() instead of render_template()
