# Plotly Violin Charts - Quick Start Guide

## 🚀 Getting Started

### 1. Start the Application

```bash
cd frontend
npm start
```

### 2. Navigate to Violin Charts

1. Open the application in your browser
2. Click on the **🎻 BNB Violins** tab
3. You'll see the filter options

### 3. Generate Your First Chart

1. **Select Metric**: Choose "Price per Night" or "Days per Stay"
2. **Select Years**: Pick one or more years (default: current year)
3. **Filter (Optional)**: Choose specific listings or channels
4. **Click**: "Generate Violin Charts" button

### 4. Explore the Charts

Two charts will appear:

- **By Listing**: Compare distributions across properties
- **By Channel**: Compare distributions across booking platforms

## 🎯 Understanding the Visualization

### Violin Shape

```
     ╱╲
    ╱  ╲      ← Wider = More data points at this value
   ╱ ▓▓ ╲     ← Box plot shows quartiles
  ╱  ▓▓  ╲    ← Orange line = Mean
 ╱   ▓▓   ╲
━━━━━━━━━━━━
```

### What Each Part Means:

- **Violin Width**: Data density (wider = more bookings at that price)
- **Blue Box**: Interquartile range (Q1 to Q3)
- **White Line in Box**: Median value
- **Orange Line**: Mean (average) value
- **Thin Lines**: Whiskers showing min/max

## 🖱️ Interactive Features

### Zoom In

1. Click and drag to select an area
2. Chart zooms to that region
3. Great for examining specific price ranges

### Pan Around

1. Hold Shift key
2. Click and drag to move the view
3. Explore different parts of the chart

### Reset View

- Double-click anywhere on the chart
- Returns to original view

### Hover for Details

- Move mouse over any violin
- See exact values and statistics
- Tooltip shows: name, value, count

### Download Chart

1. Hover over chart
2. Click camera icon in toolbar
3. Downloads as PNG image

## 📊 Reading the Statistics Table

Below each chart, you'll find a detailed table:

| Column     | Meaning             | Example |
| ---------- | ------------------- | ------- |
| **Count**  | Number of bookings  | 45      |
| **Min**    | Lowest value        | €65.00  |
| **Q1**     | 25th percentile     | €85.00  |
| **Median** | Middle value (50th) | €95.00  |
| **Mean**   | Average             | €97.50  |
| **Q3**     | 75th percentile     | €110.00 |
| **Max**    | Highest value       | €150.00 |
| **Range**  | Max - Min           | €85.00  |

## 💡 Common Use Cases

### 1. Compare Pricing Strategies

**Question**: Which listing has the most consistent pricing?

**How to Check**:

- Look at violin width
- Narrow violin = consistent pricing
- Wide violin = variable pricing

### 2. Identify Outliers

**Question**: Are there unusual prices?

**How to Check**:

- Look at the tails (top/bottom of violin)
- Long thin tails = outliers present
- Check the Min/Max in the table

### 3. Find Peak Prices

**Question**: What's the most common price?

**How to Check**:

- Find the widest part of the violin
- That's where most bookings occur
- Compare to Mean and Median

### 4. Compare Channels

**Question**: Which channel has higher prices?

**How to Check**:

- Switch to "By Channel" chart
- Compare violin positions (higher = more expensive)
- Check Mean values in the table

### 5. Analyze Booking Length

**Question**: How long do guests typically stay?

**How to Check**:

- Select "Days per Stay" metric
- Look at the median in the table
- Check violin shape for patterns

## 🎨 Customization Options

### Available Filters:

- **Years**: Multi-select (2020, 2021, 2022, etc.)
- **Listings**: All or specific property
- **Channels**: All or specific platform (Airbnb, Booking.com, etc.)
- **Metric**: Price per Night or Days per Stay

### Tips:

- Start with all data, then filter down
- Compare year-over-year by selecting multiple years
- Use single listing to see channel differences
- Use single channel to see listing differences

## 🔍 Troubleshooting

### No Data Showing?

- ✅ Check if you selected at least one year
- ✅ Verify filters aren't too restrictive
- ✅ Ensure backend API is running
- ✅ Check browser console for errors

### Chart Not Interactive?

- ✅ Make sure JavaScript is enabled
- ✅ Try refreshing the page
- ✅ Check if Plotly.js loaded (no console errors)

### Slow Loading?

- ⏱️ First load takes longer (Plotly.js is ~3MB)
- ⏱️ Subsequent loads are cached and faster
- ⏱️ Large datasets may take a few seconds

## 📱 Mobile Support

The charts work on mobile devices:

- Touch to see tooltips
- Pinch to zoom
- Swipe to pan
- Tap toolbar for options

## 🎓 Learning More

### Understanding Violin Plots:

- [Wikipedia: Violin Plot](https://en.wikipedia.org/wiki/Violin_plot)
- [Plotly Documentation](https://plotly.com/javascript/violin/)

### Statistical Concepts:

- **Median**: Middle value (50% above, 50% below)
- **Mean**: Average of all values
- **Quartiles**: Divide data into 4 equal parts
- **IQR**: Interquartile Range (Q3 - Q1)
- **KDE**: Kernel Density Estimation (the violin shape)

## 🚨 Quick Tips

1. **Start Simple**: Use default settings first
2. **Compare Gradually**: Add filters one at a time
3. **Use Zoom**: Examine interesting patterns up close
4. **Check Statistics**: Table provides exact numbers
5. **Export Charts**: Download for reports/presentations
6. **Hover Everything**: Tooltips reveal details
7. **Reset Often**: Double-click to start fresh

## 📞 Need Help?

If you encounter issues:

1. Check the browser console (F12)
2. Verify API endpoint is responding
3. Review the full documentation in `VIOLIN_CHARTS_PLOTLY.md`
4. Check the comparison guide in `VIOLIN_CHARTS_COMPARISON.md`

---

**Happy Analyzing! 🎻📊**
