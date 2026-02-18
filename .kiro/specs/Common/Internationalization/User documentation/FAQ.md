# Language Support - Frequently Asked Questions

Common questions about using myAdmin in multiple languages.

---

## General Questions

### What languages does myAdmin support?

myAdmin is available in:

- **🇳🇱 Nederlands (Dutch)** - Primary language
- **🇬🇧 English** - Secondary language

All features, menus, buttons, messages, and reports are fully translated in both languages.

### Is everything translated?

Yes! Every user-facing element is translated:

- ✅ All navigation menus and buttons
- ✅ All form labels and input fields
- ✅ All messages (success, error, warning)
- ✅ All reports and charts
- ✅ All email notifications
- ✅ Date and number formatting

### Can I request a new language?

Currently, myAdmin supports Dutch and English. If your organization needs additional languages, please contact your system administrator to discuss options.

---

## Changing Language

### How do I change my language?

1. Navigate to the **Dashboard** (main page)
2. Click the **language selector** in the top-right corner (shows current language like "🇳🇱 Nederlands")
3. Select your preferred language from the dropdown menu
4. The page will refresh in your chosen language

### Where is the language selector?

The language selector is located in the **top-right corner of the Dashboard header**, next to your user profile menu.

**Note**: It only appears on the Dashboard page. If you're on another page (Reports, Banking, STR, Admin), navigate back to the Dashboard first.

### Can I change language while working on something?

Yes! You can switch languages at any time. Your work is automatically saved, and the page will refresh in the new language without losing any data.

### What happens when I switch languages?

When you switch languages:

1. The page refreshes immediately
2. All text appears in the new language
3. Dates and numbers are reformatted to match the language
4. Your preference is saved for future sessions
5. You're redirected to the Dashboard

---

## Language Preferences

### Is my language choice saved?

Yes! Your language preference is saved in two places:

1. **Your browser** (localStorage) - for immediate use
2. **Your user account** (AWS Cognito) - for persistence across devices

This means your language choice persists:

- ✅ Across all pages as you navigate
- ✅ After logging out and back in
- ✅ On all your devices (computer, tablet, phone)
- ✅ In system emails sent to you

### Will my language choice affect other users?

No. Each user has their own language preference. Your choice only affects what you see in your own session.

### What language will I see when I first log in?

New users see the **default language set by your organization** (usually Dutch for Dutch businesses). You can change it immediately using the language selector on the Dashboard.

### Can I use different languages on different devices?

Your language preference is saved to your user account, so you'll see the **same language on all devices** where you're logged in. This ensures a consistent experience.

### What if I clear my browser data?

If you clear your browser's localStorage, the language preference will be reloaded from your user account (AWS Cognito) the next time you log in. Your preference is not lost.

---

## Dates and Numbers

### How do date formats differ between languages?

**Dutch (Nederlands):**

- Format: DD-MM-YYYY
- Example: 18-02-2026 (18 February 2026)
- Separator: Hyphen (-)

**English:**

- Format: MM/DD/YYYY
- Example: 2/18/2026 (February 18, 2026)
- Separator: Slash (/)

### How do number formats differ?

**Dutch (Nederlands):**

- Thousands separator: Period (.)
- Decimal separator: Comma (,)
- Example: 1.234,56

**English:**

- Thousands separator: Comma (,)
- Decimal separator: Period (.)
- Example: 1,234.56

### How should I enter dates?

Enter dates in the format for your selected language:

- **Dutch**: DD-MM-YYYY (e.g., 18-02-2026)
- **English**: MM/DD/YYYY (e.g., 2/18/2026)

Most date pickers will show the correct format automatically.

### How should I enter numbers?

Enter numbers using the decimal separator for your language:

- **Dutch**: Use comma for decimals (e.g., 1234,56)
- **English**: Use period for decimals (e.g., 1234.56)

The system will interpret numbers correctly based on your language setting.

### What about currency?

Currency is displayed as EUR (€) in both languages, but the number formatting differs:

- **Dutch**: €1.234,56
- **English**: €1,234.56

---

## Reports and Exports

### Are reports translated?

Yes! All reports are fully translated:

- Report titles and headers
- Column names
- Chart labels and legends
- Filter labels
- Button text

### Are Excel exports translated?

Yes. Excel exports include:

- Translated column headers
- Properly formatted dates (based on your language)
- Properly formatted numbers (based on your language)
- Translated sheet names (where applicable)

### Can I generate a report in a different language?

Reports are generated in your currently selected language. To generate a report in a different language:

1. Switch your language using the language selector
2. Navigate to the report page
3. Generate the report

### Do charts and graphs change language?

Yes! All chart elements are translated:

- Axis labels
- Legend items
- Tooltips
- Data labels

---

## Email Notifications

### What language are emails sent in?

System emails (like user invitations) are sent in **your preferred language**. If you haven't set a preference yet, emails use your organization's default language.

### Can I change the language of emails I receive?

Yes. Change your language preference using the language selector on the Dashboard. Future emails will be sent in your new preferred language.

### What about emails already sent?

Previously sent emails remain in the language they were sent in. Only new emails will use your updated language preference.

### Are all emails translated?

The following system emails are translated:

- ✅ User invitation emails
- ✅ Password reset emails (handled by AWS Cognito)
- ✅ Account update notifications

Note: Some emails are handled by AWS Cognito and may have limited translation options.

---

## Technical Questions

### Does language affect system performance?

No. Language selection has no impact on system performance. All translations are loaded efficiently and switching languages is instant.

### Can I use the system in one language and receive emails in another?

No. Email language matches your user language preference. Both use the same setting to ensure consistency.

### What if a translation is incorrect or unclear?

If you find a translation that seems incorrect or could be improved, please report it to your system administrator. We continuously improve translations based on user feedback.

### Are technical terms translated?

Some technical terms remain in English for consistency:

- API endpoints
- Database field names
- Technical error codes
- System configuration terms

User-facing labels and descriptions are always translated.

---

## Troubleshooting

### I can't find the language selector

**Solution**: The language selector only appears on the **Dashboard page**. If you're on another page (Reports, Banking, STR, Admin), click "Dashboard" in the navigation menu to return to the main page.

### The page didn't refresh after changing language

**Solution**: The page should refresh automatically. If it doesn't:

1. Manually refresh your browser (F5 or Ctrl+R)
2. If the problem persists, clear your browser cache and try again

### Some text is still in the wrong language

**Solution**: This is rare but can happen if:

1. Your browser cache is outdated - Clear cache and refresh
2. The page didn't fully reload - Hard refresh (Ctrl+Shift+R)
3. You're viewing cached content - Log out and log back in

If the problem persists, contact support.

### Dates are showing in the wrong format

**Solution**:

1. Check that you've selected the correct language
2. The date format automatically matches your language choice
3. If dates are still wrong, try switching to the other language and back again
4. Clear your browser cache if the issue persists

### Numbers are showing in the wrong format

**Solution**:

1. Verify your language selection (Dutch uses 1.234,56 / English uses 1,234.56)
2. The number format automatically matches your language choice
3. If numbers are still wrong, refresh the page
4. Clear your browser cache if the issue persists

### Emails are in the wrong language

**Solution**:

1. Check your language preference on the Dashboard
2. Change your language using the language selector
3. Wait a few minutes for the preference to sync
4. New emails will be sent in your updated language

Note: Previously sent emails remain in their original language.

### I switched language but reports are still in the old language

**Solution**:

1. After switching language, navigate to the report page again
2. Regenerate the report (don't use cached version)
3. The new report will be in your selected language

### The language selector disappeared

**Solution**: The language selector only appears on the Dashboard page. Navigate back to the Dashboard to access it.

---

## Best Practices

### When should I set my language?

Set your language preference **when you first log in** to ensure the best experience from the start.

### Should I switch languages frequently?

You can switch languages as often as needed, but it's best to **choose one language and stick with it** for consistency, especially when:

- Working on reports
- Entering data
- Collaborating with team members

### What language should I use for data entry?

Use the language you're most comfortable with. The system stores data in a language-neutral format, so it can be viewed correctly in any language.

### Can I use different languages for different tasks?

Yes, but be aware that:

- Date formats differ between languages
- Number formats differ between languages
- Switching languages frequently may cause confusion

For consistency, we recommend using one language for all tasks.

---

## Support

### Where can I get help?

If you have questions or need assistance:

1. **Check this FAQ** for common questions and solutions
2. **Read the User Guide** for detailed instructions
3. **Contact your administrator** for organization-specific settings
4. **Reach out to support** for technical issues

### How do I report a translation issue?

If you find a translation that's incorrect or could be improved:

1. Note the exact location (page, button, message)
2. Note what the translation says
3. Note what it should say
4. Contact your system administrator with this information

We appreciate your feedback and continuously improve translations based on user input.

### Can I get training in my language?

Yes! Training materials and support are available in both Dutch and English. Contact your administrator to arrange training in your preferred language.

---

## Quick Tips

✅ **Set your language first** when you log in for the first time

✅ **Use the Dashboard** to access the language selector

✅ **Pay attention to date formats** when entering data (DD-MM-YYYY vs MM/DD/YYYY)

✅ **Use the correct decimal separator** for your language (comma vs period)

✅ **Regenerate reports** after switching languages to see them in the new language

✅ **Be consistent** - choose one language and use it for all tasks

✅ **Check your email language** matches your preference

✅ **Clear browser cache** if you experience translation issues

---

**Last Updated**: February 2026
**Version**: 1.0
