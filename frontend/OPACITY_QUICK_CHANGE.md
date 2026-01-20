# Quick Guide: Changing Violin Plot Opacity

## Current Setting

**File**: `frontend/src/components/myAdminReports.tsx`  
**Line**: ~1442

```typescript
const plotData = sortedGroups.map(
  (name) =>
    ({
      type: "violin",
      y: grouped[name],
      name: name,
      box: {
        visible: true,
        fillcolor: "rgba(49, 130, 206, 0.5)", // Box fill transparency
        line: {
          color: "rgb(49, 130, 206)",
          width: 2,
        },
      },
      meanline: {
        visible: true,
        color: "rgb(245, 101, 0)", // Orange mean line
        width: 2,
      },
      line: {
        color: "rgb(49, 130, 206)", // Violin outline color
        width: 2,
      },
      fillcolor: "rgba(49, 130, 206, 0.3)", // Violin fill color + alpha
      opacity: 0.6, // ← THIS CONTROLS OVERALL TRANSPARENCY
      points: false,
      hoveron: "violins+points",
      hovertemplate:
        "<b>%{fullData.name}</b><br>" + "Value: %{y}<br>" + "<extra></extra>",
    }) as any,
);
```

## Quick Changes

### Make More Solid (Bold Look)

```typescript
opacity: 0.8,  // Change from 0.6 to 0.8
```

### Make More Transparent (Subtle Look)

```typescript
opacity: 0.4,  // Change from 0.6 to 0.4
```

### Make Completely Solid

```typescript
opacity: 1.0,  // Change from 0.6 to 1.0
```

## Visual Preview

```
opacity: 0.3          opacity: 0.6 (Current)    opacity: 0.9
Very Light            Balanced                  Very Bold

   ░░░░░                  ▓▓▓▓▓                    █████
  ░░░░░░░                ▓▓▓▓▓▓▓                  ███████
 ░░░░░░░░░              ▓▓▓▓▓▓▓▓▓                █████████
░░░░░░░░░░░            ▓▓▓▓▓▓▓▓▓▓▓              ███████████

Subtle                 Professional              Strong Impact
Good for 10+ violins   Good for 5-10 violins    Good for 2-5 violins
```

## Step-by-Step to Change

1. **Open the file**:

   ```
   frontend/src/components/myAdminReports.tsx
   ```

2. **Find the line** (around line 1442):

   ```typescript
   opacity: 0.6,
   ```

3. **Change the value**:

   ```typescript
   opacity: 0.8,  // Your new value (0.0 to 1.0)
   ```

4. **Save the file**

5. **Refresh your browser** (if dev server is running)

## Recommended Values

| Violins | Opacity | Reason                         |
| ------- | ------- | ------------------------------ |
| 2-3     | 0.8     | Bold, clear comparison         |
| 4-6     | 0.7     | Strong but not overwhelming    |
| 7-10    | 0.6     | **Current - Balanced**         |
| 11-15   | 0.5     | Prevents clutter               |
| 16+     | 0.4     | Many violins need transparency |

## Pro Tip: Dynamic Opacity

Want opacity to adjust automatically based on number of violins?

```typescript
const plotData = sortedGroups.map((name) => {
  // Calculate opacity based on number of groups
  const violinCount = sortedGroups.length;
  const dynamicOpacity =
    violinCount <= 5
      ? 0.8
      : violinCount <= 10
        ? 0.6
        : violinCount <= 15
          ? 0.5
          : 0.4;

  return {
    type: "violin",
    y: grouped[name],
    name: name,
    // ... other properties ...
    opacity: dynamicOpacity, // ← Automatically adjusts!
    // ...
  };
});
```

## Testing Different Values

1. Start with current: `0.6`
2. Try bolder: `0.8`
3. Try lighter: `0.4`
4. Pick what looks best with your data

## What Else Can You Customize?

### Violin Fill Color

```typescript
fillcolor: 'rgba(49, 130, 206, 0.3)',  // Blue with 30% alpha
// Try: 'rgba(245, 101, 0, 0.3)'  // Orange
// Try: 'rgba(72, 187, 120, 0.3)'  // Green
```

### Violin Outline Width

```typescript
line: {
  color: 'rgb(49, 130, 206)',
  width: 2  // Try: 1 (thinner) or 3 (thicker)
}
```

### Mean Line Color

```typescript
meanline: {
  visible: true,
  color: 'rgb(245, 101, 0)',  // Orange
  width: 2
}
```

### Box Plot Visibility

```typescript
box: {
  visible: true,  // Try: false to hide box plot
  fillcolor: 'rgba(49, 130, 206, 0.5)',
  // ...
}
```

## Common Combinations

### Bold & Professional

```typescript
opacity: 0.8,
fillcolor: 'rgba(49, 130, 206, 0.4)',
line: { width: 2 }
```

### Subtle & Clean

```typescript
opacity: 0.4,
fillcolor: 'rgba(49, 130, 206, 0.2)',
line: { width: 1 }
```

### High Contrast

```typescript
opacity: 0.9,
fillcolor: 'rgba(49, 130, 206, 0.6)',
line: { width: 3 }
```

## Need Help?

If you want to experiment but aren't sure what looks good:

1. Try `0.8` first (bolder)
2. If too heavy, try `0.5` (lighter)
3. Settle on something between that feels right

The current `0.6` is a safe, professional default that works well in most cases!
