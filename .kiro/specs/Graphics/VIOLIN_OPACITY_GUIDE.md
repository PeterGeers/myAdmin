# Violin Plot Opacity Guide

## Understanding Opacity

The `opacity` property controls how transparent or solid the violin shapes appear.

## Opacity Values & Use Cases

### opacity: 1.0 (Solid)

```typescript
opacity: 1.0;
```

**Appearance**: Completely solid, no transparency

**Best for**:

- ✅ Single violin plots
- ✅ Non-overlapping violins
- ✅ Maximum visual impact
- ✅ Print/presentation materials

**Drawbacks**:

- ❌ Hides box plot if too dark
- ❌ Overlapping violins obscure each other
- ❌ Can look too heavy

### opacity: 0.8 (Mostly Solid)

```typescript
opacity: 0.8;
```

**Appearance**: Slightly transparent, strong presence

**Best for**:

- ✅ Clear, bold visualizations
- ✅ Few violins (2-4)
- ✅ When you want emphasis
- ✅ Dark backgrounds

**Drawbacks**:

- ⚠️ Still quite opaque
- ⚠️ Box plot may be less visible

### opacity: 0.6 (Balanced) ⭐ CURRENT

```typescript
opacity: 0.6;
```

**Appearance**: Semi-transparent, balanced

**Best for**:

- ✅ Multiple violins (5-10)
- ✅ General purpose use
- ✅ Good box plot visibility
- ✅ Professional appearance
- ✅ Overlapping data

**Why it's default**:

- Perfect balance of visibility and transparency
- Box plot clearly visible inside
- Works well with multiple violins
- Professional statistical look

### opacity: 0.4 (Light)

```typescript
opacity: 0.4;
```

**Appearance**: Quite transparent, subtle

**Best for**:

- ✅ Many violins (10+)
- ✅ Overlapping distributions
- ✅ Focus on box plots
- ✅ Minimalist style

**Drawbacks**:

- ⚠️ Violin shape less prominent
- ⚠️ May look washed out

### opacity: 0.2 (Very Light)

```typescript
opacity: 0.2;
```

**Appearance**: Very transparent, barely visible

**Best for**:

- ✅ Background context
- ✅ Emphasis on box plots only
- ✅ Extremely crowded charts

**Drawbacks**:

- ❌ Violin shape hard to see
- ❌ Loses the point of violin plots

## Visual Comparison

```
Data Density Visualization at Different Opacities:

opacity: 1.0          opacity: 0.6          opacity: 0.3
████████████          ▓▓▓▓▓▓▓▓▓▓▓▓          ░░░░░░░░░░░░
████████████          ▓▓▓▓▓▓▓▓▓▓▓▓          ░░░░░░░░░░░░
████████████          ▓▓▓▓▓▓▓▓▓▓▓▓          ░░░░░░░░░░░░
Bold & Strong         Balanced              Subtle & Light
```

## Combining with fillcolor

Your current setup uses BOTH:

```typescript
opacity: 0.6,                           // Overall transparency
fillcolor: 'rgba(49, 130, 206, 0.3)',  // Color with alpha channel
```

### How They Interact:

- `fillcolor` alpha (0.3) = Base color transparency
- `opacity` (0.6) = Additional transparency layer
- **Combined effect**: 0.3 × 0.6 = 0.18 effective opacity

### Recommendation:

Choose ONE approach for clarity:

**Option A: Use opacity only**

```typescript
opacity: 0.6,
fillcolor: 'rgb(49, 130, 206)',  // No alpha in color
```

**Option B: Use fillcolor alpha only**

```typescript
opacity: 1.0,
fillcolor: 'rgba(49, 130, 206, 0.6)',  // Alpha in color
```

Both achieve similar results, but Option A is cleaner.

## Adjusting Opacity in Your Code

### Current Location

File: `frontend/src/components/myAdminReports.tsx`
Line: ~1420 (in ViolinChart component)

### To Change:

```typescript
const plotData = sortedGroups.map((name) => ({
  type: "violin",
  y: grouped[name],
  name: name,
  box: { visible: true /* ... */ },
  meanline: { visible: true /* ... */ },
  line: { color: "rgb(49, 130, 206)", width: 2 },
  fillcolor: "rgba(49, 130, 206, 0.3)",
  opacity: 0.6, // ← CHANGE THIS VALUE
  // ...
}));
```

## Recommended Settings by Scenario

### Scenario 1: Few Listings (2-5)

```typescript
opacity: 0.7,
fillcolor: 'rgba(49, 130, 206, 0.4)',
```

**Result**: Bold, clear violins

### Scenario 2: Many Listings (6-15)

```typescript
opacity: 0.6,  // Current setting
fillcolor: 'rgba(49, 130, 206, 0.3)',
```

**Result**: Balanced visibility

### Scenario 3: Crowded Chart (15+)

```typescript
opacity: 0.4,
fillcolor: 'rgba(49, 130, 206, 0.3)',
```

**Result**: Prevents visual clutter

### Scenario 4: Emphasis on Box Plots

```typescript
opacity: 0.3,
fillcolor: 'rgba(49, 130, 206, 0.2)',
```

**Result**: Violin as background context

### Scenario 5: Maximum Impact (Presentations)

```typescript
opacity: 0.8,
fillcolor: 'rgba(49, 130, 206, 0.5)',
```

**Result**: Strong, professional look

## Dynamic Opacity (Advanced)

You could make opacity dynamic based on data:

```typescript
const plotData = sortedGroups.map((name) => {
  const dataCount = grouped[name].length;

  // More data points = more opacity
  const dynamicOpacity = Math.min(0.9, 0.3 + dataCount / 100);

  return {
    type: "violin",
    opacity: dynamicOpacity,
    // ...
  };
});
```

## Testing Different Opacities

Quick test in browser console:

```javascript
// After chart renders, you can modify it:
const plotDiv = document.querySelector('[data-testid="plotly-chart"]');
Plotly.restyle(plotDiv, { opacity: 0.8 }, [0]); // Change first trace
```

## Best Practices

1. **Start with 0.6**: Good default for most cases
2. **Adjust based on count**: More violins = lower opacity
3. **Consider background**: Dark backgrounds need higher opacity
4. **Test with real data**: Opacity looks different with actual distributions
5. **Be consistent**: Use same opacity across similar charts
6. **Print vs Screen**: Use higher opacity (0.7-0.8) for printed materials

## Color Psychology

The opacity also affects color perception:

- **High opacity (0.8-1.0)**: Bold, confident, attention-grabbing
- **Medium opacity (0.5-0.7)**: Professional, balanced, analytical
- **Low opacity (0.2-0.4)**: Subtle, background, contextual

## Accessibility Considerations

- **Minimum opacity**: 0.4 for users with visual impairments
- **Contrast**: Ensure violin is distinguishable from background
- **Color blindness**: Opacity helps when colors are similar

## Summary

**Current Setting**: `opacity: 0.6`

- ✅ Excellent default choice
- ✅ Works for 2-10 violins
- ✅ Good box plot visibility
- ✅ Professional appearance

**When to Change**:

- More violins → Lower opacity (0.4-0.5)
- Fewer violins → Higher opacity (0.7-0.8)
- Presentation → Higher opacity (0.8)
- Overlapping data → Lower opacity (0.4-0.5)
