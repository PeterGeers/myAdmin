// Only set API_BASE_URL when running on port 5000 (production build served by Flask)
// On port 3000 (React dev server), leave it empty so the proxy middleware handles API requests
if (window.location.port === '5000') {
  window.API_BASE_URL = 'http://localhost:5000';
} else {
  // Empty string means use relative URLs, which the proxy will intercept
  window.API_BASE_URL = '';
}