# Violin Charts with Plotly.js

## Overview

The BNB Violin Charts feature now uses **Plotly.js** for true violin plot visualization, replacing the previous Recharts box plot implementation.

## What Changed

### Before (Recharts)

- Used BarChart to simulate box plots
- No true violin shape (kernel density estimation)
- Limited interactivity
- Manual calculation of all statistics

### After (Plotly.js)

- Native violin plot support with kernel density estimation
- True violin shape showing data distribution
- Rich interactivity (zoom, pan, hover, download)
- Built-in statistical calculations
- Professional-looking visualizations

## Features

### Visualization

- **Violin Shape**: Shows the full distribution of data using kernel density estimation
- **Box Plot Overlay**: Displays quartiles (Q1, median, Q3) inside the violin
- **Mean Line**: Orange line showing the mean value
- **Interactive Tooltips**: Hover to see individual data points and statistics

### Interactivity

- **Zoom**: Click and drag to zoom into specific areas
- **Pan**: Shift + drag to pan across the chart
- **Reset**: Double-click to reset view
- **Download**: Export chart as PNG image
- **Hover**: See detailed statistics for each group

### Statistics Table

Below each chart, a comprehensive statistics table shows:

- Count of data points
- Minimum, Q1, Median, Mean, Q3, Maximum
- Range (Max - Min)

## Usage

Navigate to the **🎻 BNB Violins** tab and:

1. Select metric: "Price per Night" or "Days per Stay"
2. Choose years to analyze
3. Filter by listings or channels (optional)
4. Click "Generate Violin Charts"

Two charts will be generated:

- Distribution by Listing
- Distribution by Channel

## Technical Details

### Dependencies

```json
{
  "react-plotly.js": "^2.x",
  "plotly.js": "^2.x",
  "@types/react-plotly.js": "^2.x",
  "@types/plotly.js": "^2.x"
}
```

### Component Location

`frontend/src/components/myAdminReports.tsx` - ViolinChart component

### Data Structure

The component expects data in the format:

```typescript
{
  listing: string,    // or channel
  channel: string,    // or listing
  value: number       // the metric value
}[]
```

### Customization

The violin plots are styled to match your application theme:

- Blue violins with semi-transparent fill
- Orange mean line
- White background for better visibility
- Responsive sizing

## Performance

### Bundle Size

Plotly.js adds approximately 3MB to the bundle size. This is acceptable for:

- Professional statistical visualizations
- Rich interactivity requirements
- Desktop/web applications

### Optimization Tips

- Plotly is loaded only when the component is rendered
- Consider code splitting if bundle size becomes an issue
- The library is well-optimized for rendering performance

## Browser Support

Plotly.js works in all modern browsers:

- Chrome, Firefox, Safari, Edge (latest versions)
- Requires JavaScript enabled
- WebGL support recommended for best performance

## Future Enhancements

Possible improvements:

- Add more violin plot options (side-by-side, split violins)
- Export data as CSV from the chart
- Add statistical tests (t-test, ANOVA)
- Customize colors per group
- Add trend lines or annotations
