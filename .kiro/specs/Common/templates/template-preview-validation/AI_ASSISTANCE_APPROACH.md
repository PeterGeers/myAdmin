# AI-Powered Template Assistance - Privacy-First Approach

**Date**: January 31, 2026  
**Status**: Recommended Solution

---

## Problem Statement

**Original Approach** (❌ Not Recommended):

- Give SysAdmin read access to all tenant templates
- SysAdmin helps tenants fix template errors
- **Issues**:
  - Privacy violation (SysAdmin sees tenant-specific customizations)
  - Security risk (access to external systems)
  - Scalability problem (manual support doesn't scale)
  - Tenant trust issue (data privacy concerns)

---

## Improved Solution: AI-Powered Self-Service

**New Approach** (✅ Recommended):

- Use **OpenRouter AI** to help tenants fix their own templates
- No SysAdmin access to tenant data
- Self-service, instant help
- Privacy-preserving

---

## How It Works

### User Flow

```
1. Tenant Admin uploads template
   ↓
2. Validation fails (missing placeholders, syntax errors, etc.)
   ↓
3. User clicks "🤖 Get AI Help" button
   ↓
4. System sends to OpenRouter AI:
   - Validation errors
   - Template code (sanitized - no tenant data)
   - Template type
   - Required placeholders
   ↓
5. AI analyzes and returns:
   - Problem explanation
   - Specific fix suggestions
   - Code examples
   - Auto-fix option (if applicable)
   ↓
6. User reviews AI suggestions
   ↓
7. User can:
   - Apply auto-fixes (one click)
   - Manually apply suggestions
   - Reject and edit manually
   ↓
8. Re-validate template
   ↓
9. Approve and activate
```

### Example Interaction

**Validation Error**:

```
❌ Missing required placeholder '{{ invoice_number }}'
❌ Unclosed <div> tag at line 45
```

**User clicks "Get AI Help"**

**AI Response**:

```
🤖 Analysis:
Your template is missing the invoice number placeholder, which is
essential for generating unique invoice identifiers. There's also
an unclosed div tag in the header section.

Suggested Fixes:

1. Missing {{ invoice_number }}
   Suggestion: Add the invoice number in the header
   Code Example:
   <div class="invoice-header">
     <h2>Invoice #{{ invoice_number }}</h2>
     <p>Date: {{ invoice_date }}</p>
   </div>
   Location: Line 15-20 (header section)
   ✨ Auto-fixable: Yes

2. Unclosed <div> tag
   Suggestion: Close the div tag at line 45
   Code Example:
   </div>  <!-- Close header div -->
   Location: Line 45
   ✨ Auto-fixable: Yes

Confidence: High
```

**User clicks "Apply All Auto-Fixes"**

**Result**: Template updated, ready to re-validate

---

## Privacy & Security

### What AI Sees ✅

- Template HTML structure
- Validation error messages
- Template type (e.g., "str_invoice_nl")
- Required placeholder list

### What AI Does NOT See ❌

- Actual tenant data (invoices, bookings, financial records)
- Sample data used for preview
- Tenant name or identifying information
- Google Drive credentials
- Database credentials
- Any PII (personally identifiable information)

### Data Sanitization

Before sending to AI, we sanitize the template:

```python
# Remove hardcoded emails
template = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                  'email@example.com', template)

# Remove hardcoded phone numbers
template = re.sub(r'\b\d{10,}\b', '0123456789', template)

# Remove hardcoded addresses (basic)
# Keep placeholders like {{ address }}
```

**Result**: AI only sees template structure, not tenant data.

---

## Benefits

### For Tenants

- ✅ **Privacy**: No one else sees their templates
- ✅ **Speed**: Instant help (no waiting for support)
- ✅ **Learning**: Understand what's wrong and how to fix it
- ✅ **Confidence**: AI explains issues clearly

### For System

- ✅ **Scalability**: AI handles unlimited requests
- ✅ **Consistency**: Same quality help for all tenants
- ✅ **Cost-effective**: Cheaper than manual support
- ✅ **24/7 availability**: No business hours limitation

### For SysAdmin

- ✅ **No privacy concerns**: Never see tenant data
- ✅ **Focus on platform**: Monitor system health, not individual templates
- ✅ **Metrics only**: See aggregated stats, not individual cases

---

## Technical Implementation

### Backend API

```python
# POST /api/tenant-admin/templates/ai-help
{
  "template_type": "str_invoice_nl",
  "template_content": "<html>...</html>",
  "validation_errors": [...]
}

# Response
{
  "success": true,
  "ai_suggestions": {
    "analysis": "...",
    "fixes": [...],
    "auto_fix_available": true,
    "confidence": "high"
  }
}
```

### Frontend Component

```typescript
<AIHelpButton
  templateType="str_invoice_nl"
  templateContent={template}
  validationErrors={errors}
  onFixesApplied={(fixed) => setTemplate(fixed)}
/>
```

### AI Integration

- **Provider**: OpenRouter (supports multiple AI models)
- **Model**: Claude 3.5 Sonnet (or GPT-4)
- **Cost**: ~$0.01-0.05 per request
- **Response Time**: 2-5 seconds

---

## Cost Analysis

### AI API Costs

- **Per Request**: ~$0.01-0.05 (depending on template size)
- **Expected Usage**: 10-50 requests/month per tenant
- **Monthly Cost**: $0.50-2.50 per active tenant
- **Annual Cost**: $6-30 per tenant

### Compared to Manual Support

- **Manual Support**: $50-100 per ticket (30-60 min @ $100/hr)
- **AI Support**: $0.01-0.05 per request
- **Savings**: 1000x-10000x cost reduction

**ROI**: Pays for itself after 1-2 support tickets avoided per tenant.

---

## SysAdmin Role (Revised)

### What SysAdmin CAN Do ✅

1. **Monitor System Health**
   - View aggregated metrics (# templates uploaded, validation success rate)
   - Monitor AI API usage and costs
   - Track system performance

2. **View Anonymized Patterns**
   - Common validation errors (aggregated)
   - AI suggestion acceptance rate
   - Template types most used

3. **Configure AI Settings**
   - Enable/disable AI assistance
   - Set AI model and parameters
   - Configure cost limits

4. **Platform Management**
   - Manage Cognito users
   - Configure platform settings
   - Monitor infrastructure

### What SysAdmin CANNOT Do ❌

1. ❌ View tenant-specific templates
2. ❌ View tenant data (invoices, reports, etc.)
3. ❌ Access tenant Google Drive
4. ❌ Modify tenant templates
5. ❌ See tenant customizations

**Result**: Complete tenant data privacy maintained.

---

## Fallback Strategy

If AI is unavailable or fails:

1. **Show Generic Help**
   - Common error explanations
   - Link to documentation
   - Example templates

2. **Manual Editing**
   - User can still edit template manually
   - Re-validate after changes

3. **Support Ticket** (Last Resort)
   - User can request human help
   - Support team guides without seeing template
   - User implements fixes themselves

---

## Future Enhancements

### Phase 2

- **Learning from Fixes**: Track which AI suggestions work best
- **Template Library**: AI-generated starter templates
- **Proactive Suggestions**: AI suggests improvements even when valid

### Phase 3

- **Visual Editor**: AI-powered drag-and-drop template builder
- **A/B Testing**: AI suggests template variations to test
- **Performance Optimization**: AI suggests ways to make templates faster

---

## Comparison: Old vs New Approach

| Aspect           | Old (SysAdmin Access)        | New (AI Assistance)              |
| ---------------- | ---------------------------- | -------------------------------- |
| **Privacy**      | ❌ SysAdmin sees tenant data | ✅ No one sees tenant data       |
| **Speed**        | ❌ Hours/days (ticket queue) | ✅ Seconds (instant)             |
| **Scalability**  | ❌ Limited by support team   | ✅ Unlimited (AI scales)         |
| **Cost**         | ❌ $50-100 per ticket        | ✅ $0.01-0.05 per request        |
| **Availability** | ❌ Business hours only       | ✅ 24/7                          |
| **Consistency**  | ❌ Varies by support person  | ✅ Consistent quality            |
| **Learning**     | ❌ User doesn't learn        | ✅ User learns from explanations |
| **Trust**        | ❌ Privacy concerns          | ✅ Full privacy                  |

---

## Recommendation

**✅ Implement AI-Powered Template Assistance**

This approach:

- Maintains tenant data privacy
- Provides better user experience
- Scales infinitely
- Costs less than manual support
- Builds tenant trust
- Empowers self-service

**❌ Do NOT give SysAdmin access to tenant templates**

This would:

- Violate tenant privacy
- Create security risks
- Not scale
- Reduce tenant trust
- Create support bottleneck

---

## Next Steps

1. ✅ Update requirements document (remove SysAdmin access story)
2. ✅ Add AI assistance to design document
3. ⏭️ Add AI assistance tasks to implementation plan
4. ⏭️ Set up OpenRouter API account
5. ⏭️ Implement AITemplateAssistant service
6. ⏭️ Implement AI Help frontend component
7. ⏭️ Test with real validation errors
8. ⏭️ Monitor AI suggestion quality
9. ⏭️ Iterate and improve prompts

---

## Conclusion

AI-powered template assistance is the **privacy-first, scalable, cost-effective** solution for helping tenants fix template errors. It maintains complete tenant data privacy while providing instant, high-quality help.

**This is the recommended approach for Phase 2.6 implementation.**
