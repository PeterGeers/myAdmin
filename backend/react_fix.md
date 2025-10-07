# React Key Prop Fix

In your PDFUploadForm.tsx file around line 130, change this:

```tsx
{folders.map(folder => (
  <option value={folder}>{folder}</option>
))}
```

To this:

```tsx
{folders.map((folder, index) => (
  <option key={index} value={folder}>{folder}</option>
))}
```

Or if folders have unique names:

```tsx
{folders.map(folder => (
  <option key={folder} value={folder}>{folder}</option>
))}
```