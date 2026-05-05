/**
 * Type declaration for plotly.js-dist-min.
 *
 * The plotly.js-dist-min package is a minified bundle of plotly.js
 * that doesn't ship its own TypeScript declarations. This declaration
 * re-exports the types from @types/plotly.js which is already installed
 * as a dev dependency.
 */
declare module "plotly.js-dist-min" {
  import Plotly from "plotly.js";
  export default Plotly;
}
