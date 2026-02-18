# Language Selector Screenshots Guide

This document describes the visual elements of the language selector feature for documentation purposes.

## Language Selector Location

The language selector is located in the **top-right corner** of the **main Dashboard header**, next to the user profile menu.

**Important**: The language selector only appears on the Dashboard page, not on other pages (Reports, Banking, STR, Admin).

### Header Layout

```
┌────────────────────────────────────────────────────────────────┐
│ myAdmin Dashboard                    🇳🇱 Nederlands ▼  [User ▼] │
└────────────────────────────────────────────────────────────────┘
```

**Key Elements:**

- Application title on the left
- Language selector in the center-right (flag + language name + dropdown arrow)
- User profile menu on the far right

---

## Language Selector States

### 1. Default State (Closed)

**Dutch Selected:**

```
┌──────────────────┐
│ 🇳🇱 Nederlands ▼ │
└──────────────────┘
```

**English Selected:**

```
┌──────────────┐
│ 🇬🇧 English ▼ │
└──────────────┘
```

**Visual Elements:**

- Flag emoji (🇳🇱 or 🇬🇧)
- Language name (Nederlands or English)
- Dropdown arrow (▼)
- Light gray background
- Rounded corners
- Hover effect (slightly darker background)

### 2. Open State (Dropdown Menu)

**When Dutch is Selected:**

```
┌──────────────────┐
│ 🇳🇱 Nederlands ▼ │
├──────────────────┤
│ 🇳🇱 Nederlands ✓ │  ← Currently selected (checkmark)
│ 🇬🇧 English      │  ← Available option
└──────────────────┘
```

**When English is Selected:**

```
┌──────────────┐
│ 🇬🇧 English ▼ │
├──────────────┤
│ 🇳🇱 Nederlands │  ← Available option
│ 🇬🇧 English ✓  │  ← Currently selected (checkmark)
└──────────────┘
```

**Visual Elements:**

- Dropdown menu appears below the button
- White background with shadow
- Each option shows flag + language name
- Currently selected language has a checkmark (✓)
- Hover effect on menu items (light blue background)

---

## User Interaction Flow

### Step 1: Initial View

User sees the language selector in the header showing their current language.

### Step 2: Click to Open

User clicks the language selector button. The dropdown menu opens showing both language options.

### Step 3: Select Language

User clicks on their preferred language. The menu closes and the page refreshes.

### Step 4: Confirmation

The page reloads with all text in the selected language. The language selector now shows the new language.

---

## Visual Design Specifications

### Colors

**Button (Closed State):**

- Background: Light gray (#F7FAFC)
- Text: Dark gray (#2D3748)
- Border: None
- Hover: Slightly darker gray (#EDF2F7)

**Dropdown Menu:**

- Background: White (#FFFFFF)
- Border: Light gray (#E2E8F0)
- Shadow: Subtle drop shadow
- Text: Dark gray (#2D3748)

**Menu Item (Hover):**

- Background: Light blue (#EBF8FF)
- Text: Dark blue (#2C5282)

**Selected Item:**

- Checkmark: Green (#38A169)
- Background: Same as hover state

### Typography

**Button Text:**

- Font: System font (Segoe UI, Arial, sans-serif)
- Size: 14px
- Weight: Medium (500)

**Menu Items:**

- Font: System font
- Size: 14px
- Weight: Normal (400)

### Spacing

**Button:**

- Padding: 8px 12px
- Border radius: 6px
- Gap between flag and text: 8px

**Dropdown Menu:**

- Padding: 4px 0
- Border radius: 6px
- Item padding: 8px 12px
- Gap between items: 2px

### Icons

**Flags:**

- Size: 20px × 20px (emoji)
- Position: Left of language name

**Dropdown Arrow:**

- Size: 12px × 12px
- Position: Right of language name
- Rotation: 0° (closed), 180° (open)

**Checkmark:**

- Size: 16px × 16px
- Position: Right of language name
- Color: Green (#38A169)

---

## Responsive Behavior

### Desktop (> 1024px)

- Full language name displayed (Nederlands, English)
- Flag + name + arrow visible
- Dropdown menu aligned to the right

### Tablet (768px - 1024px)

- Full language name displayed
- Same layout as desktop
- Dropdown menu aligned to the right

### Mobile (< 768px)

- Language name may be abbreviated (NL, EN)
- Flag always visible
- Dropdown menu full width or aligned to the right

---

## Accessibility Features

### Keyboard Navigation

- **Tab**: Focus on language selector
- **Enter/Space**: Open dropdown menu
- **Arrow Up/Down**: Navigate menu items
- **Enter**: Select language
- **Escape**: Close menu

### Screen Reader Support

- Button labeled: "Change language, current language: Nederlands"
- Menu items labeled: "Nederlands" and "English"
- Selected item announced: "Nederlands, selected"

### Visual Indicators

- Focus outline when keyboard navigating
- Clear hover states
- Checkmark for selected language
- High contrast text

---

## Example Screenshots Needed

For complete user documentation, the following screenshots should be captured:

### 1. Language Selector in Header

**Filename**: `language-selector-header.png`
**Description**: Full application header showing language selector location
**Annotations**: Arrow pointing to language selector with label "Click here to change language"

### 2. Language Selector Closed (Dutch)

**Filename**: `language-selector-dutch.png`
**Description**: Close-up of language selector showing "🇳🇱 Nederlands"
**Annotations**: None needed

### 3. Language Selector Closed (English)

**Filename**: `language-selector-english.png`
**Description**: Close-up of language selector showing "🇬🇧 English"
**Annotations**: None needed

### 4. Language Selector Open (Dutch Selected)

**Filename**: `language-selector-menu-dutch.png`
**Description**: Dropdown menu open with Nederlands selected (checkmark visible)
**Annotations**: Arrow pointing to checkmark with label "Currently selected"

### 5. Language Selector Open (English Selected)

**Filename**: `language-selector-menu-english.png`
**Description**: Dropdown menu open with English selected (checkmark visible)
**Annotations**: Arrow pointing to checkmark with label "Currently selected"

### 6. Before and After Language Switch

**Filename**: `language-switch-comparison.png`
**Description**: Side-by-side comparison of same page in Dutch and English
**Annotations**: Labels showing "Dutch" and "English" above each screenshot

### 7. Date Format Comparison

**Filename**: `date-format-comparison.png`
**Description**: Side-by-side showing date formats (18-02-2026 vs 2/18/2026)
**Annotations**: Labels showing "Dutch format" and "English format"

### 8. Number Format Comparison

**Filename**: `number-format-comparison.png`
**Description**: Side-by-side showing number formats (1.234,56 vs 1,234.56)
**Annotations**: Labels showing "Dutch format" and "English format"

### 9. Report in Dutch

**Filename**: `report-dutch.png`
**Description**: Sample report showing Dutch labels and formatting
**Annotations**: Highlight key translated elements

### 10. Report in English

**Filename**: `report-english.png`
**Description**: Same report showing English labels and formatting
**Annotations**: Highlight key translated elements

---

## Screenshot Capture Guidelines

### Preparation

1. Use a clean test environment with sample data
2. Ensure browser window is at standard resolution (1920×1080)
3. Clear browser cache before capturing
4. Use consistent zoom level (100%)

### Capture Settings

- **Format**: PNG (for clarity)
- **Resolution**: High DPI (2x for retina displays)
- **Cropping**: Include relevant context, remove unnecessary UI
- **Annotations**: Use arrows, boxes, and labels where helpful

### Consistency

- Use same browser for all screenshots (Chrome recommended)
- Use same theme/styling
- Use same sample data where possible
- Maintain consistent window size

### Privacy

- Remove or blur any sensitive data
- Use generic tenant names (e.g., "Demo Company")
- Use placeholder user names (e.g., "John Doe")
- Use sample financial data (not real transactions)

---

## Screenshot Storage

Screenshots should be stored in:

```
.kiro/specs/Common/Internationalization/User documentation/screenshots/
```

**Naming Convention:**

- Use descriptive names with hyphens
- Include language if applicable
- Use lowercase
- Examples:
  - `language-selector-header.png`
  - `language-selector-menu-dutch.png`
  - `report-comparison-dutch-english.png`

---

## Using Screenshots in Documentation

### In User Guide

Embed screenshots with descriptive captions:

```markdown
![Language Selector Location](screenshots/language-selector-header.png)
_The language selector is located in the top-right corner of the header_
```

### In Training Materials

Use annotated screenshots with step numbers:

```markdown
1. Click the language selector
   ![Step 1](screenshots/step-1-click-selector.png)

2. Choose your language
   ![Step 2](screenshots/step-2-choose-language.png)
```

### In FAQ

Use comparison screenshots to illustrate differences:

```markdown
**Q: How do date formats differ?**

Dutch format: ![Dutch dates](screenshots/date-format-dutch.png)
English format: ![English dates](screenshots/date-format-english.png)
```

---

## Updating Screenshots

Screenshots should be updated when:

- UI design changes significantly
- New features are added to the language selector
- Language options are added or removed
- Branding or styling is updated

**Update Frequency**: Review screenshots quarterly or after major releases

---

**Note**: This guide describes the visual elements for documentation purposes. Actual screenshots should be captured from the running application and stored in the `screenshots/` subdirectory.

**Last Updated**: February 2026
**Version**: 1.0
