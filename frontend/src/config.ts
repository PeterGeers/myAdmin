// API Configuration
//
// The Flask API base URL is resolved from APP_ENV via the Environment_Resolver
// (`./config/appEnv` → `RESOLVED.flaskApiBaseUrl`), NOT hardcoded to a physical
// location nor inferred from the browser protocol/hostname or any other incidental
// signal (Req 21.2-21.4). The former `getApiBaseUrl()` switch — which read
// `window.API_BASE_URL` and `window.location.protocol` and fell back to a
// hardcoded local Flask URL literal — has been removed; the environment is decided
// once, by the explicit APP_ENV selector, and this module merely consumes the
// resolved value (one decision, many consumers).
//
// Public shape is preserved: `API_BASE_URL` and `buildApiUrl` keep their existing
// signatures so importers are unaffected; only the value source changes.
import { RESOLVED } from './config/appEnv';

export const API_BASE_URL = RESOLVED.flaskApiBaseUrl;

// Helper function to build API URLs
export const buildApiUrl = (endpoint: string, params?: URLSearchParams): string => {
  const url = `${API_BASE_URL}${endpoint}`;
  return params ? `${url}?${params.toString()}` : url;
};
