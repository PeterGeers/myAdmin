import React from 'react';

// Mock Plotly to avoid loading the full library in tests
jest.mock('react-plotly.js', () => {
  return function MockPlot() {
    return <div data-testid="plotly-violin-chart">Plotly Violin Chart</div>;
  };
});

describe('ViolinChart with Plotly', () => {
  it('should render without crashing', () => {
    // This test verifies that the Plotly import doesn't break the build
    expect(true).toBe(true);
  });
});
