# Design — End-User Documentation

## Technology Choice: MkDocs + Material Theme

- Python-based (matches backend stack)
- Material theme gives search, responsive layout, print support, callouts out of the box
- Markdown authoring — easy for anyone to edit
- Static output — fast, hostable anywhere
- Install: `pip install mkdocs-material`

## Documentation Site Structure

```
docs/                              # Root docs folder
├── mkdocs.yml                     # MkDocs configuration
├── docs/
│   ├── index.md                   # Home / Getting Started
│   ├── getting-started/
│   │   ├── overview.md            # What is myAdmin?
│   │   ├── first-login.md         # Logging in and navigating
│   │   ├── test-vs-production.md  # When to use which mode
│   │   └── common-workflows.md    # Quick overview of key tasks
│   │
│   ├── banking/
│   │   ├── index.md               # Banking overview
│   │   ├── importing-statements.md
│   │   ├── reviewing-transactions.md
│   │   ├── pattern-matching.md
│   │   └── handling-duplicates.md
│   │
│   ├── invoices/
│   │   ├── index.md
│   │   ├── uploading-invoices.md
│   │   ├── ai-extraction.md
│   │   ├── editing-approving.md
│   │   └── google-drive.md
│   │
│   ├── str/
│   │   ├── index.md
│   │   ├── importing-bookings.md
│   │   ├── realized-vs-planned.md
│   │   └── revenue-summaries.md
│   │
│   ├── str-pricing/
│   │   ├── index.md
│   │   ├── viewing-recommendations.md
│   │   ├── event-pricing.md
│   │   └── applying-suggestions.md
│   │
│   ├── reports/
│   │   ├── index.md
│   │   ├── dashboards.md
│   │   ├── pnl-balance-sheets.md
│   │   └── exporting-excel.md
│   │
│   ├── tax/
│   │   ├── index.md
│   │   ├── btw.md
│   │   ├── income-tax-ib.md
│   │   └── toeristenbelasting.md
│   │
│   ├── pdf-validation/
│   │   ├── index.md
│   │   └── checking-fixing-links.md
│   │
│   ├── admin/
│   │   ├── index.md
│   │   ├── tenant-management.md
│   │   ├── user-management.md
│   │   ├── docker-deployment.md
│   │   ├── database-admin.md
│   │   ├── audit-logging.md
│   │   └── troubleshooting.md
│   │
│   ├── changelog.md
│   ├── faq.md
│   └── glossary.md
│
└── overrides/                     # Theme customizations
```

## MkDocs Configuration

```yaml
# mkdocs.yml
site_name: myAdmin Documentation
site_description: User documentation for myAdmin financial management
theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.top
    - search.suggest
    - search.highlight
    - content.tabs.link
    - toc.integrate
  palette:
    - scheme: default
      primary: red
      accent: red

plugins:
  - search
  - print-site
  - i18n:
      default_language: nl
      languages:
        nl:
          name: Nederlands
          build: true
        en:
          name: English
          build: true

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences
  - attr_list
  - toc:
      permalink: true

nav:
  - Home: index.md
  - Getting Started:
      - Overview: getting-started/overview.md
      - First Login: getting-started/first-login.md
      - Test vs Production: getting-started/test-vs-production.md
      - Common Workflows: getting-started/common-workflows.md
  - Banking:
      - Overview: banking/index.md
      - Importing Statements: banking/importing-statements.md
      - Reviewing Transactions: banking/reviewing-transactions.md
      - Pattern Matching: banking/pattern-matching.md
      - Handling Duplicates: banking/handling-duplicates.md
  - Invoices:
      - Overview: invoices/index.md
      - Uploading: invoices/uploading-invoices.md
      - AI Extraction: invoices/ai-extraction.md
      - Editing & Approving: invoices/editing-approving.md
      - Google Drive: invoices/google-drive.md
  - STR:
      - Overview: str/index.md
      - Importing Bookings: str/importing-bookings.md
      - Realized vs Planned: str/realized-vs-planned.md
      - Revenue Summaries: str/revenue-summaries.md
  - STR Pricing:
      - Overview: str-pricing/index.md
      - Recommendations: str-pricing/viewing-recommendations.md
      - Event Pricing: str-pricing/event-pricing.md
      - Applying Suggestions: str-pricing/applying-suggestions.md
  - Reports:
      - Overview: reports/index.md
      - Dashboards: reports/dashboards.md
      - P&L & Balance Sheets: reports/pnl-balance-sheets.md
      - Excel Export: reports/exporting-excel.md
  - Tax:
      - Overview: tax/index.md
      - BTW: tax/btw.md
      - Income Tax (IB): tax/income-tax-ib.md
      - Toeristenbelasting: tax/toeristenbelasting.md
  - PDF Validation:
      - Overview: pdf-validation/index.md
      - Checking & Fixing Links: pdf-validation/checking-fixing-links.md
  - Admin Guide:
      - Overview: admin/index.md
      - Tenants: admin/tenant-management.md
      - Users: admin/user-management.md
      - Docker: admin/docker-deployment.md
      - Database: admin/database-admin.md
      - Audit Logging: admin/audit-logging.md
      - Troubleshooting: admin/troubleshooting.md
  - Changelog: changelog.md
  - FAQ: faq.md
  - Glossary: glossary.md
```

## Page Template

Every module page follows this structure:

```markdown
# [Task Title]

> Brief one-line description of what this page covers.

## Overview

What this feature does and when you'd use it.

## What You'll Need

- Prerequisites
- Permissions needed

## Step by Step

### 1. [First step]

Description with screenshot if needed.

!!! tip
Helpful tip related to this step.

## Tips

- Useful shortcuts or best practices

## Troubleshooting

| Problem | Cause | Solution |
| ------- | ----- | -------- |
| [Issue] | [Why] | [Fix]    |
```

## Callout Conventions

- `!!! tip` — helpful advice for power users
- `!!! info` — background context
- `!!! warning` — could cause problems
- `!!! danger` — data loss or irreversible action

## In-App Help Components

### Architecture: Header-Based Integration

Instead of adding help buttons to each page individually, the HelpButton is placed once in the shared page header in `App.tsx`. Every page in myAdmin uses the same header pattern:

```tsx
<Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
  <HStack justify="space-between">
    <HStack>
      <Button>← Back</Button>
      <Heading>📄 Page Title</Heading>
    </HStack>
    <HStack spacing={3}>
      <TenantSelector size="sm" />
      <HelpButton page={currentPage} />   {/* ← single integration point */}
      <UserMenu ... />
    </HStack>
  </HStack>
</Box>
```

This approach:

- Covers all pages with a single code change in `App.tsx`
- Uses the existing `currentPage` state to determine which docs section to open
- Sits naturally next to `TenantSelector` and `UserMenu`
- No need to modify individual module components

### File Structure

```
frontend/src/components/help/
├── HelpButton.tsx        # Question mark icon + drawer trigger (receives `page` prop)
├── HelpDrawer.tsx        # Slide-out panel rendering Markdown
├── FieldHelp.tsx         # Info icon with tooltip + "Learn more"
├── helpLinks.ts          # PageType-to-docs mapping (uses currentPage, not routes)
└── index.ts              # Barrel export
```

### PageType-to-Docs Mapping

Since myAdmin uses `currentPage` state (not URL routes), the mapping uses `PageType` values:

```typescript
// helpLinks.ts
import { PageType } from "../../App";

const DOCS_BASE_URL = process.env.REACT_APP_DOCS_URL || "/docs";

export const helpLinks: Record<string, string> = {
  banking: "banking/",
  pdf: "invoices/",
  str: "str/",
  "str-invoice": "str/",
  "str-pricing": "str-pricing/",
  "str-reports": "str/revenue-summaries/",
  "fin-reports": "reports/",
  powerbi: "reports/dashboards/",
  "pdf-validate": "pdf-validation/",
  admin: "admin/",
  "tenant-admin": "tenant-admin/",
  settings: "tenant-admin/tenant-settings/",
  menu: "", // homepage
};

export const getDocsLanguage = (): string => {
  const browserLang = navigator.language.substring(0, 2);
  return browserLang === "nl" ? "nl" : "en";
};

export const getHelpUrl = (page: string): string => {
  const lang = getDocsLanguage();
  const langPrefix = lang === "nl" ? "" : "/en";
  const section = helpLinks[page] || "";
  return `${DOCS_BASE_URL}${langPrefix}/${section}`;
};
```

### HelpButton Component

```typescript
// HelpButton.tsx
interface HelpButtonProps {
  page: string;  // currentPage from App.tsx
}

const HelpButton: React.FC<HelpButtonProps> = ({ page }) => {
  const { isOpen, onOpen, onClose } = useDisclosure();
  const helpUrl = getHelpUrl(page);

  return (
    <>
      <IconButton
        aria-label="Help"
        icon={<QuestionOutlineIcon />}
        size="sm"
        variant="ghost"
        color="gray.300"
        _hover={{ color: "orange.400" }}
        onClick={onOpen}
      />
      <HelpDrawer isOpen={isOpen} onClose={onClose} helpUrl={helpUrl} />
    </>
  );
};
```

### HelpDrawer Behavior

1. Click help icon → Drawer slides in from right
2. Fetches Markdown from docs URL
3. Renders with `react-markdown`
4. "Open in full docs" link at top
5. Fallback: if fetch fails, opens docs URL in new tab

### App.tsx Integration (Single Change)

```tsx
// In each page's header HStack (right side):
<HStack spacing={3}>
  <TenantSelector size="sm" />
  <HelpButton page={currentPage} />
  <UserMenu
    onLogout={logout}
    onSettings={() => setCurrentPage("settings")}
    mode={status.mode}
  />
</HStack>
```

Since every page repeats this header pattern, a helper function can reduce duplication:

```tsx
const renderPageHeader = (title: string, icon: string) => (
  <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
    <HStack justify="space-between">
      <HStack>
        <Button
          size="sm"
          colorScheme="orange"
          onClick={() => setCurrentPage("menu")}
        >
          ← Back
        </Button>
        <Heading color="orange.400" size="lg">
          {icon} {title}
        </Heading>
      </HStack>
      <HStack spacing={3}>
        <TenantSelector size="sm" />
        <HelpButton page={currentPage} />
        <UserMenu
          onLogout={logout}
          onSettings={() => setCurrentPage("settings")}
          mode={status.mode}
        />
      </HStack>
    </HStack>
  </Box>
);
```

### Tooltip Content Map

| Location               | Tooltip Text                                                  | Docs Link                          |
| ---------------------- | ------------------------------------------------------------- | ---------------------------------- |
| Apply Patterns         | "Automatically assigns accounts based on historical patterns" | banking/pattern-matching           |
| Check Duplicates       | "Checks if transactions already exist in the database"        | banking/handling-duplicates        |
| AI Extract             | "Uses AI to read invoice details from the PDF"                | invoices/ai-extraction             |
| Test/Production toggle | "Test mode uses a separate database — safe for trying things" | getting-started/test-vs-production |

## Deployment

### Serve from Backend (Recommended)

```python
@app.route('/docs/')
@app.route('/docs/<path:path>')
def serve_docs(path='index.html'):
    return send_from_directory('docs/site', path)
```

Keeps everything in one deployment, no CORS issues for the help drawer.

### Build Commands

```bash
cd docs
pip install mkdocs-material mkdocs-print-site-plugin
mkdocs serve      # Local preview at http://localhost:8000
mkdocs build      # Output to docs/site/
```

### Environment Variable

```
# frontend/.env
REACT_APP_DOCS_URL=/docs
```
