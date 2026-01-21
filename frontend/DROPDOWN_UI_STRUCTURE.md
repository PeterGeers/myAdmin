# Dropdown UI Structure

## Visual Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back    📈 myAdmin Reports                          [Test]   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Category:                    Report:                            │
│  ┌──────────────────────┐    ┌────────────────────────────┐    │
│  │ 🏠 BNB Reports    ▼ │    │ 🏠 BNB Revenue          ▼ │    │
│  └──────────────────────┘    └────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│                    [Selected Report Content]                     │
│                                                                   │
│  • Filters                                                       │
│  • Charts                                                        │
│  • Tables                                                        │
│  • Export buttons                                                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Dropdown Interactions

### Category Dropdown (First Level)

```
┌──────────────────────┐
│ 🏠 BNB Reports    ▼ │  ← Click to open
└──────────────────────┘
         ↓
┌──────────────────────┐
│ 🏠 BNB Reports      │  ← Currently selected (highlighted)
│ 💰 Financial Reports │
└──────────────────────┘
```

### Report Dropdown (Second Level)

**When BNB Reports selected:**

```
┌────────────────────────────┐
│ 🏠 BNB Revenue          ▼ │  ← Click to open
└────────────────────────────┘
         ↓
┌────────────────────────────┐
│ 🏠 BNB Revenue            │  ← Currently selected
│ 🏡 BNB Actuals            │
│ 🎻 BNB Violins            │
│ 🔄 BNB Terugkerend        │
│ 📈 BNB Future             │
│ 🏨 Toeristenbelasting     │
└────────────────────────────┘
```

**When Financial Reports selected:**

```
┌────────────────────────────┐
│ 💰 Mutaties (P&L)       ▼ │  ← Click to open
└────────────────────────────┘
         ↓
┌────────────────────────────┐
│ 💰 Mutaties (P&L)         │  ← Currently selected
│ 📊 Actuals                │
│ 🧾 BTW aangifte           │
│ 📈 View ReferenceNumber   │
│ 📋 Aangifte IB            │
└────────────────────────────┘
```

## User Flow

### Scenario 1: Viewing BNB Revenue (Default)

```
1. Page loads
   ↓
2. Category: "🏠 BNB Reports" (default)
   ↓
3. Report: "🏠 BNB Revenue" (first in category)
   ↓
4. BNB Revenue report displays
```

### Scenario 2: Switching to Financial Report

```
1. User clicks Category dropdown
   ↓
2. Selects "💰 Financial Reports"
   ↓
3. Report dropdown auto-updates to show financial reports
   ↓
4. Report auto-selects "💰 Mutaties (P&L)" (first in category)
   ↓
5. Mutaties report displays
```

### Scenario 3: Switching Reports Within Category

```
1. User is viewing "🏠 BNB Revenue"
   ↓
2. Clicks Report dropdown
   ↓
3. Selects "🏡 BNB Actuals"
   ↓
4. BNB Actuals report displays
   ↓
5. Category remains "🏠 BNB Reports"
```

## Color Scheme

### Category Dropdown

- **Button**: Orange (`orange.500`)
- **Hover**: Darker orange (`orange.600`)
- **Selected**: Orange background (`orange.600`)

### Report Dropdown

- **Button**: Blue (`blue.500`)
- **Hover**: Darker blue (`blue.600`)
- **Selected**: Blue background (`blue.600`)

### Background

- **Main**: Dark gray (`gray.800`)
- **Selector Box**: Medium gray (`gray.700`)
- **Menu**: Dark gray (`gray.700`)

## Responsive Behavior

### Desktop (> 768px)

```
┌─────────────────────────────────────────────────┐
│  Category: [Dropdown]    Report: [Dropdown]     │
└─────────────────────────────────────────────────┘
```

### Mobile (< 768px)

```
┌─────────────────────────┐
│  Category:              │
│  [Dropdown - Full Width]│
│                         │
│  Report:                │
│  [Dropdown - Full Width]│
└─────────────────────────┘
```

## Comparison: Old vs New

### Old Interface (11 Tabs)

```
┌────────────────────────────────────────────────────────────────────┐
│ [💰 Mutaties] [🏠 BNB Revenue] [📊 Actuals] [🏡 BNB Actuals] ... │
└────────────────────────────────────────────────────────────────────┘
```

**Issues:**

- Crowded horizontal space
- Hard to scan 11 options
- Poor mobile experience
- No logical grouping

### New Interface (2 Dropdowns)

```
┌─────────────────────────────────────────────────────────────────┐
│  Category: [🏠 BNB Reports ▼]    Report: [🏠 BNB Revenue ▼]   │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits:**

- Clean, organized layout
- Logical grouping (BNB vs Financial)
- Better mobile support
- Easier to navigate
- Scalable (easy to add more reports)

## Accessibility

### Keyboard Navigation

- **Tab**: Move between dropdowns
- **Enter/Space**: Open dropdown
- **Arrow Keys**: Navigate options
- **Enter**: Select option
- **Escape**: Close dropdown

### Screen Readers

- Dropdowns have proper ARIA labels
- Selected state announced
- Category changes announced
- Report changes announced

## State Management

```typescript
// Component State
const [selectedCategory, setSelectedCategory] = useState<Category>('bnb');
const [selectedReport, setSelectedReport] = useState(reports.bnb[0]);

// When category changes:
1. Update selectedCategory
2. Auto-select first report in new category
3. Update selectedReport
4. Re-render with new report

// When report changes:
1. Update selectedReport
2. Re-render with new report
3. Category remains unchanged
```

## Performance Considerations

### Current Implementation

- All reports loaded in MyAdminReports component
- Only selected report rendered
- Tab switching is instant (no loading)

### Future Optimization

- Lazy load report components
- Code split by report
- Cache report data
- Preload next likely report

## Browser Support

- ✅ Chrome/Edge (latest)
- ✅ Firefox (latest)
- ✅ Safari (latest)
- ✅ Mobile browsers
- ⚠️ IE11 (not tested, likely needs polyfills)
