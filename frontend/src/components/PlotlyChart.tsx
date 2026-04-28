/**
 * Custom Plotly Chart wrapper using plotly.js-dist-min
 * 
 * Uses the react-plotly.js factory pattern to create a Plot component
 * backed by the minified Plotly bundle (~1MB vs ~3MB for full plotly.js).
 */
import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

const Plot = createPlotlyComponent(Plotly);
export default Plot;
