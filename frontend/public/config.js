// Set API_BASE_URL based on environment
// - GitHub Pages: Use Railway backend URL
// - Local port 5000: Use local Flask server
// - Local port 3000: Use empty string for proxy
if (window.location.hostname === 'petergeers.github.io') {
  // Production deployment on GitHub Pages
  window.API_BASE_URL = 'https://invigorating-celebration-production.up.railway.app';
} else if (window.location.port === '5000') {
  // Local production build served by Flask
  window.API_BASE_URL = 'http://localhost:5000';
} else {
  // Local development (port 3000) - use proxy
  window.API_BASE_URL = '';
}