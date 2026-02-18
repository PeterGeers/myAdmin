# myAdmin

Comprehensive administrative tooling with ReactJS frontend and Python backend for financial transaction processing.

## Quick Start

```psh
# Start both servers
.\start.ps1

# Or manually:
cd backend && python app.py  # Port 5000
cd frontend && npm start     # Port 3000
```

## Components

### 📄 Import Invoices

- Upload PDFs, EML, and MHTML files to Google Drive or local storage
- AI‑powered universal invoice data extraction via OpenRouter API
- Traditional vendor‑specific parsers as fallback (250+ formats)
- Searchable folder dropdown with auto‑selection
- Edit and approve transactions before persisting
- MySQL storage with metadata

### 🏦 Banking Processor

- Process CSV bank statements (Rabobank format)
- Pattern matching for automatic account assignment
- Duplicate detection & filtering
- Bulk transaction import

### 🏠 STR (Short‑Term‑Rental) Processor

- Process Airbnb/Booking.com revenue files
- Separate realized vs planned bookings
- Generate future revenue summaries
- Multi‑platform support

### 💰 STR Pricing Optimizer

- AI‑powered pricing recommendations with business logic
- Historical vs recommended ADR comparison
- Quarterly summary tables per listing
- Monthly trend analysis with interactive charts
- Event‑based pricing uplifts
- Guest‑fee adjustments (child‑friendly)
- 14‑month pricing strategy generation

### 📊 myAdmin Reports

- Interactive dashboards with Recharts
- P&L statements & balance sheets
- BNB revenue analytics (violin/box plots)
- BNB returning‑guest analysis
- Aangifte IB (Income‑Tax) declarations with VW logic
- Excel/XLSX export
- Reference‑number validation

### 🔍 PDF Validation System

- Validate Google‑Drive URLs in transaction records
- Real‑time progress with dynamic progress bar
- Year & admin filtering
- Automatic file/folder URL resolution
- Manual update for broken links
- Gmail‑URL detection for manual verification

## 💡 OpenRouter Tool‑Call ID

When sending a request to the OpenRouter API, include a `tool_call_id` field that is **exactly 9 alphanumeric characters** (a‑z, A‑Z, 0‑9).  
Example:

```json
{
  "model": "meta-llama/llama-3.2-3b-instruct:free",
  "messages": [...],
  "tool_call_id": "a1B2c3D4E"
}
```

If you generate the ID automatically, validate the length and character set before sending. A compliant ID prevents the `400 Provider returned error`.

## Database

- **MySQL**: Main transaction storage
- **Tables**: `mutaties`, `bnb`, `bnbplanned`, `bnbfuture`, `pricing_recommendations`, `pricing_events`, `listings`
- **Views**: `vw_mutaties` for reporting (VW logic)
- **Config**: `.env` file with credentials
- **Pricing**: AI insights storage & business‑logic pricing

## Test / Production Mode

### Environment Switching

Toggle between test & production using `.env`:

```env
# Production (default)
TEST_MODE=false
DB_NAME=finance
FACTUREN_FOLDER_ID=your_production_folder_id
FACTUREN_FOLDER_NAME=Facturen
OPENROUTER_API_KEY=your_openrouter_api_key

# Test
TEST_MODE=true
TEST_DB_NAME=testfinance
TEST_FACTUREN_FOLDER_ID=your_test_folder_id
TEST_FACTUREN_FOLDER_NAME=testFacturen
```

### OpenRouter API Setup

The OpenRouter API powers AI features including invoice extraction and template validation:

1. **Create Account**: Visit [OpenRouter.ai](https://openrouter.ai/) and sign up
2. **Generate API Key**: Navigate to your dashboard and create a new API key
3. **Configure**: Add the key to your `.env` file:
   ```env
   OPENROUTER_API_KEY=sk-or-v1-your-api-key-here
   ```
4. **Verify**: The key should start with `sk-or-v1-` and be approximately 64 characters

**Features enabled by OpenRouter:**

- Universal invoice data extraction (AI-powered)
- Template validation assistance
- Smart error analysis and auto-fix suggestions
- STR pricing optimization recommendations

**Note**: Some features will fall back to traditional methods if the API key is not configured.

### Features

- Automatic database and Google‑Drive folder switching
- Mode indicator displayed in all function headers
- Route & schema validation at startup

## Git Management

```bash
# Commit with timestamp:
.\scripts\setup\gitUpdate.ps1

# Commit with custom message:
.\scripts\setup\gitUpdate.ps1 "Your message here"
```

## Internationalization (i18n)

myAdmin supports multiple languages with comprehensive internationalization:

### Supported Languages

- **Dutch (nl)** - Primary language
- **English (en)** - Secondary language

### Features

- **Language Selector**: Switch languages from any page header
- **Persistent Preferences**: Language choice saved to localStorage and AWS Cognito
- **Localized Formatting**: Dates, numbers, and currency adapt to selected language
  - Dutch: 18-02-2026, 1.234,56, €1.234,56
  - English: 2/18/2026, 1,234.56, €1,234.56
- **Translated UI**: All user-facing text translated (1,485+ translation keys)
- **Translated Emails**: User invitation emails sent in user's preferred language
- **API Language Support**: Backend responds in requested language via X-Language header

### For Developers

See comprehensive documentation in `.kiro/specs/Common/Internationalization/`:

- **DEVELOPER_GUIDE.md** - Complete guide for working with translations
- **FORMATTING_GUIDE.md** - Date, number, and currency formatting utilities
- **TRANSLATION_WORKFLOW.md** - Translation process from development to deployment

Quick reference:

```typescript
// Use translations in components
import { useTypedTranslation } from '../hooks/useTypedTranslation';

function MyComponent() {
  const { t, i18n } = useTypedTranslation('common');

  return (
    <div>
      <h1>{t('myFeature.title')}</h1>
      <p>{formatDate(new Date(), i18n.language)}</p>
      <p>{formatCurrency(1234.56, i18n.language)}</p>
    </div>
  );
}
```

### Translation Completeness

Run automated checks to verify all translations are complete:

```bash
# Frontend (1,485 keys)
cd frontend
node scripts/check-translations.js

# Backend
cd backend
python scripts/check_translations.py
```

## Tech Stack

- **Frontend**: React, TypeScript, Chakra UI, Recharts, react-i18next
- **Backend**: Python, Flask, MySQL, Google‑Drive, Gmail APIs, Flask-Babel
- **AI Integration**: OpenRouter API (GPT‑3.5‑turbo) for invoice extraction
- **Processing**: PyPDF2, pdfplumber, pandas, openpyxl
- **Pricing**: Business logic + AI correction factors
- **Export**: HTML & XLSX (R script logic)
- **Realtime**: Server‑Sent Events for progress tracking
- **i18n**: react-i18next (frontend), Flask-Babel (backend), date-fns (formatting)
