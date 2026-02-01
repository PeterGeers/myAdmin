# Template Management - Development Guide

## Quick Links

- [README.md](./README.md) - Component documentation and API reference
- [ACCESSIBILITY.md](./ACCESSIBILITY.md) - Accessibility implementation guide
- [STYLING.md](./STYLING.md) - Styling guide and audit results

## Overview

This guide provides technical details for developers working on the Template Management feature.

## Project Structure

```
TemplateManagement/
├── README.md                    # Main documentation
├── DEVELOPMENT_GUIDE.md         # This file
├── ACCESSIBILITY.md             # Accessibility guide
├── STYLING.md                   # Styling guide
├── index.ts                     # Component exports
├── TemplateManagement.tsx       # Main container
├── TemplateUpload.tsx           # File upload
├── TemplatePreview.tsx          # Preview iframe
├── ValidationResults.tsx        # Validation display
├── FieldMappingEditor.tsx       # JSON editor
├── TemplateApproval.tsx         # Approve/reject
└── AIHelpButton.tsx             # AI assistance
```

## Development Workflow

### 1. Setup

```bash
# Install dependencies
cd frontend
npm install

# Start development server
npm start
```

### 2. Component Development

**Key Principles:**

- Use Chakra UI for all styling
- Follow existing component patterns
- Maintain accessibility standards
- Add TypeScript types for all props
- Include error handling

**Example Component Structure:**

```tsx
import React from "react";
import { Box, Button, VStack } from "@chakra-ui/react";

interface MyComponentProps {
  onAction: () => void;
  loading?: boolean;
  disabled?: boolean;
}

export const MyComponent: React.FC<MyComponentProps> = ({
  onAction,
  loading = false,
  disabled = false,
}) => {
  return (
    <VStack spacing={4}>
      <Button
        onClick={onAction}
        isLoading={loading}
        isDisabled={disabled}
        colorScheme="orange"
      >
        Action
      </Button>
    </VStack>
  );
};
```

### 3. State Management

**Pattern Used:** React useState with helper functions

```tsx
const [state, setState] = useState<StateInterface>(initialState);

const updateState = (updates: Partial<StateInterface>) => {
  setState((prev) => ({ ...prev, ...updates }));
};
```

**State Structure:**

```tsx
interface TemplateManagementState {
  // Template data
  templateContent: string;
  templateType: TemplateType | "";
  fieldMappings: Record<string, any>;

  // Validation and preview
  validationResult: ValidationResult | null;
  previewHtml: string;
  sampleDataInfo: { source: string; record_count?: number } | null;

  // AI assistance
  aiSuggestions: AIHelpResponse | null;

  // UI state
  loading: boolean;
  error: string;
  success: string;

  // Step tracking
  currentStep: "upload" | "preview" | "approval";
}
```

### 4. API Integration

**Service Location:** `frontend/src/services/templateApi.ts`

**Usage Pattern:**

```tsx
import * as templateApi from "../../../services/templateApi";

// In component
const handleUpload = async (file: File, type: TemplateType) => {
  try {
    const result = await templateApi.previewTemplate(type, content);
    // Handle success
  } catch (err) {
    // Handle error
  }
};
```

**Available API Functions:**

- `previewTemplate(type, content, mappings?)` - Generate preview
- `validateTemplate(type, content)` - Validate only
- `approveTemplate(type, content, mappings?, notes?)` - Approve
- `rejectTemplate(type, reason?)` - Reject
- `getAIHelp(type, content, errors, placeholders)` - Get AI suggestions
- `applyAIFixes(content, fixes)` - Apply AI fixes

### 5. Error Handling

**Pattern:**

```tsx
try {
  // API call
  const result = await templateApi.someFunction();

  // Update state
  updateState({ success: "Operation successful" });

  // Show toast
  toast({
    title: "Success",
    description: "Operation completed",
    status: "success",
    duration: 5000,
    isClosable: true,
  });
} catch (err) {
  const errorMessage = err instanceof Error ? err.message : "Operation failed";

  // Update state
  updateState({ error: errorMessage });

  // Show toast
  toast({
    title: "Error",
    description: errorMessage,
    status: "error",
    duration: 7000,
    isClosable: true,
  });
}
```

### 6. Testing

**Unit Tests:**

```tsx
// TemplateManagement.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { TemplateManagement } from "./TemplateManagement";

describe("TemplateManagement", () => {
  it("renders upload form", () => {
    render(<TemplateManagement />);
    expect(screen.getByText("Template Management")).toBeInTheDocument();
  });

  it("handles file upload", async () => {
    render(<TemplateManagement />);
    const file = new File(["<html></html>"], "template.html", {
      type: "text/html",
    });
    const input = screen.getByLabelText("Upload HTML template file");

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText("Template validated")).toBeInTheDocument();
    });
  });
});
```

**Integration Tests:**

```tsx
// TemplateManagement.integration.test.tsx
describe("TemplateManagement Integration", () => {
  it("completes full workflow", async () => {
    // 1. Upload template
    // 2. Validate
    // 3. Preview
    // 4. Approve
    // 5. Verify saved
  });
});
```

## Code Quality Standards

### TypeScript

- ✅ All props must have interfaces
- ✅ No `any` types (use `unknown` if needed)
- ✅ Strict null checks enabled
- ✅ Return types on all functions

### Styling

- ✅ Use Chakra UI components only
- ✅ Use theme colors (`brand.orange`, `brand.gray`)
- ✅ Responsive breakpoints (`base`, `md`, `lg`)
- ✅ No inline styles or custom CSS

### Accessibility

- ✅ ARIA labels on all interactive elements
- ✅ Keyboard navigation support
- ✅ Screen reader announcements (toast)
- ✅ Color contrast WCAG AA compliant
- ✅ Focus indicators visible

### Performance

- ✅ Lazy load heavy components
- ✅ Memoize expensive calculations
- ✅ Debounce user input
- ✅ Optimize re-renders

## Common Issues & Solutions

### Issue: File upload not working

**Solution:** Check file size (max 5MB) and type (HTML only)

```tsx
if (file.size > 5 * 1024 * 1024) {
  throw new Error("File size exceeds 5MB limit");
}

if (!file.name.endsWith(".html") && !file.name.endsWith(".htm")) {
  throw new Error("Only HTML files are allowed");
}
```

### Issue: Preview not displaying

**Solution:** Check iframe sandbox attribute and srcDoc

```tsx
<Box
  as="iframe"
  srcDoc={previewHtml}
  sandbox="allow-same-origin" // No scripts!
  w="100%"
  h="100%"
/>
```

### Issue: Validation errors not showing

**Solution:** Check ValidationResult structure

```tsx
interface ValidationResult {
  is_valid: boolean;
  errors: ValidationError[];
  warnings: ValidationError[];
  checks_performed?: string[];
}
```

### Issue: Toast not announcing to screen readers

**Solution:** Ensure proper status and description

```tsx
toast({
  title: "Action completed", // Required
  description: "Details here", // Required for screen readers
  status: "success", // Required
  duration: 5000,
  isClosable: true,
});
```

## Debugging Tips

### Enable Debug Logging

```tsx
// Add to component
useEffect(() => {
  console.log("State changed:", state);
}, [state]);
```

### Check API Responses

```tsx
const result = await templateApi.previewTemplate(type, content);
console.log("API Response:", result);
```

### Verify ARIA Attributes

```tsx
// Use React DevTools
// Check "Accessibility" tab in browser DevTools
```

### Test Screen Reader

```bash
# Windows: NVDA (free)
# macOS: VoiceOver (built-in, Cmd+F5)
# Test all interactive elements
```

## Performance Optimization

### Memoize Expensive Calculations

```tsx
const requiredPlaceholders = useMemo(
  () => getRequiredPlaceholders(templateType),
  [templateType],
);
```

### Debounce User Input

```tsx
const debouncedValidate = useMemo(
  () =>
    debounce((content: string) => {
      validateTemplate(content);
    }, 500),
  [],
);
```

### Lazy Load Components

```tsx
const AIHelpButton = lazy(() => import('./AIHelpButton'));

// In render
<Suspense fallback={<Spinner />}>
  <AIHelpButton ... />
</Suspense>
```

## Deployment Checklist

- [ ] All TypeScript errors resolved
- [ ] All ESLint warnings addressed
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] Accessibility tests passing
- [ ] Manual testing on mobile
- [ ] Manual testing on tablet
- [ ] Manual testing on desktop
- [ ] Screen reader testing (NVDA/VoiceOver)
- [ ] Keyboard navigation testing
- [ ] Cross-browser testing (Chrome, Firefox, Safari, Edge)
- [ ] Performance testing (Lighthouse)
- [ ] Security review completed
- [ ] Documentation updated

## Resources

### Internal Documentation

- [README.md](./README.md) - Component documentation
- [ACCESSIBILITY.md](./ACCESSIBILITY.md) - Accessibility guide
- [STYLING.md](./STYLING.md) - Styling guide

### External Resources

- [Chakra UI Documentation](https://chakra-ui.com/docs)
- [React TypeScript Cheatsheet](https://react-typescript-cheatsheet.netlify.app/)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)

### Backend Documentation

- API Endpoints: `backend/src/tenant_admin_routes.py`
- Template Service: `backend/src/services/template_preview_service.py`
- AI Assistant: `backend/src/services/ai_template_assistant.py`

## Support

For questions or issues:

1. Check this guide and README.md
2. Review existing components for patterns
3. Check backend API documentation
4. Ask team for help

## Version History

- **v1.0.0** (2026-02-01) - Initial implementation
  - All components implemented
  - Styling and accessibility complete
  - Ready for testing
