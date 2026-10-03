/**
 * Environment_Definition (frontend) — TypeScript equivalent of the backend
 * `backend/src/environment/environment_definition.py`.
 *
 * S3 / T1.5 — The committed source of truth for the per-plane TEST and PRODUCTION
 * configuration the frontend consumes, derived from APP_ENV via the Environment_Resolver
 * (`appEnv.ts`). It mirrors the backend definition's public identifier values so the two
 * runtimes cannot drift (Requirements 2.3, 3.1-3.6, 8.1-8.2).
 *
 * Design contract (see `.kiro/specs/Common/test-environment/first-draft/design.md`):
 * - Declare TEST and PRODUCTION configuration per plane that the frontend consumes:
 *   Cognito identity, Flask API base URL, SAM API base URL, DynamoDB prefix.
 * - Use placeholders for secrets (the frontend holds NO secrets anyway — Req 3.6, 19.1).
 * - Public identifiers (pool ids/client ids) MUST match the backend definition exactly.
 * - Record TEST_URL / PROD_URL (Req 22) and test/production branch mapping (Req 23).
 * - Values are read-only (frozen) — the frontend never mutates the definition.
 *
 * IMPORTANT: keep the public identifiers below in sync with the backend's
 * `environment_definition.py` (TEST_POOL_ID / TEST_CLIENT_ID / PROD_POOL_ID / …).
 */

/** Cognito identity plane configuration for a single environment. */
export interface CognitoDef {
  /** Cognito User Pool ID (public identifier). */
  readonly poolId: string;
  /** Cognito App Client ID (public identifier). */
  readonly clientId: string;
  /**
   * Reference/placeholder for the client secret — NEVER the real value. For the
   * test pool this is empty string (the test app-client has no secret, Req 8.4).
   * The frontend never uses a client secret; this field exists only to mirror the
   * backend definition shape.
   */
  readonly clientSecretRef: string;
  /** Human-readable pool label (e.g. "myAdmin-test", "myAdmin"). */
  readonly poolLabel: string;
}

/** SAM plane configuration (as observable to the frontend) for a single environment. */
export interface SamDef {
  /** The deployed SAM/CloudFormation stack name (e.g. "myAdmin-test"). */
  readonly stackName: string;
  /** The SAM API Gateway invoke URL clients call. */
  readonly apiBaseUrl: string;
  /** DynamoDB table prefix ("test_" for TEST, "" for PRODUCTION). */
  readonly tablePrefix: string;
  /** Cognito pool ID that the SAM authorizer validates against. */
  readonly authorizerPoolId: string;
}

/** Complete per-plane configuration the frontend consumes for a single environment. */
export interface FrontendPlaneDef {
  /** Resolved Cognito identity configuration. */
  readonly cognito: CognitoDef;
  /** The Flask API base URL the frontend calls. */
  readonly flaskApiBaseUrl: string;
  /** SAM compute plane configuration (API base URL, prefix, authorizer pool). */
  readonly sam: SamDef;
}

/** The single documented source of truth for the frontend environment configuration. */
export interface EnvironmentDefinition {
  /** TEST environment configuration (APP_ENV=test). */
  readonly test: FrontendPlaneDef;
  /** PRODUCTION environment configuration (APP_ENV=production). */
  readonly production: FrontendPlaneDef;
  /** Distinct URL serving the Test_Environment (authenticates against the test pool). */
  readonly testUrl: string;
  /** Distinct URL serving the Production_Environment (authenticates against Pool A). */
  readonly productionUrl: string;
  /** Git branch designated for TEST deployments (e.g. "test"), or null if unrecorded. */
  readonly testBranch: string | null;
  /** Git branch designated for PRODUCTION deployments (e.g. "main"), or null. */
  readonly productionBranch: string | null;
}

// -----------------------------------------------------------------------------
// Public identifiers (non-secret) — MUST match backend environment_definition.py
// -----------------------------------------------------------------------------

export const TEST_POOL_ID = 'eu-west-1_xyrlzfqbl';
export const TEST_CLIENT_ID = '43s15cm8qcgg8an85udt0e087u';
export const PROD_POOL_ID = 'eu-west-1_Hdp40eWmu';
// PROD_CLIENT_ID — the production Cognito app client id. PUBLIC, non-secret
// identifier mirroring the backend definition (the frontend never holds a secret).
export const PROD_CLIENT_ID = '66tp0087h9tfbstggonnu5aghp';

/** TEST plane definition — selected when APP_ENV=test. */
export const TEST_FRONTEND_CONFIG: FrontendPlaneDef = {
  cognito: {
    poolId: TEST_POOL_ID,
    clientId: TEST_CLIENT_ID,
    clientSecretRef: '', // test pool has no client secret (Req 8.4)
    poolLabel: 'myAdmin-test',
  },
  flaskApiBaseUrl: 'http://localhost:5000', // current TEST Flask API URL (non-normative mapping)
  // SAM plane is per MODULE; this records the members module (the one with an
  // HTTP API). stackName is the members TEST stack; the TEST API base URL is a
  // PLACEHOLDER until the `test_sam-members` stack is first deployed.
  sam: {
    stackName: 'test-sam-members',
    apiBaseUrl: 'https://PLACEHOLDER_TEST_API.execute-api.eu-west-1.amazonaws.com/test',
    tablePrefix: 'test_',
    authorizerPoolId: TEST_POOL_ID,
  },
} as const;

/** PRODUCTION plane definition — selected when APP_ENV=production. */
export const PROD_FRONTEND_CONFIG: FrontendPlaneDef = {
  cognito: {
    poolId: PROD_POOL_ID,
    clientId: PROD_CLIENT_ID,
    clientSecretRef: 'PLACEHOLDER_CLIENT_SECRET', // placeholder — frontend holds no secret
    poolLabel: 'myAdmin',
  },
  flaskApiBaseUrl: 'https://PLACEHOLDER_PRODUCTION_FLASK_API', // PROD Flask API URL
  // SAM plane is per MODULE; this records the members module (the one with an
  // HTTP API). stackName is the live members PROD stack; apiBaseUrl is the
  // deployed sam-members API Gateway invoke URL (see deploy-frontend.yml
  // VITE_MEMBERS_API_BASE_URL).
  sam: {
    stackName: 'sam-members',
    apiBaseUrl: 'https://22x6z55301.execute-api.eu-west-1.amazonaws.com/prod',
    tablePrefix: '',
    authorizerPoolId: PROD_POOL_ID,
  },
} as const;

/** The single committed environment definition the resolver reads. */
export const ENVIRONMENT_DEFINITION: EnvironmentDefinition = {
  test: TEST_FRONTEND_CONFIG,
  production: PROD_FRONTEND_CONFIG,
  testUrl: 'localhost:3000',
  productionUrl: 'app.myadmin.jabaki.nl',
  testBranch: 'test',
  productionBranch: 'main',
} as const;

// -----------------------------------------------------------------------------
// Non-normative current mapping notes (recorded for context, not the definition)
// -----------------------------------------------------------------------------
//
// Cognito plane:
// - TEST pool:  eu-west-1_xyrlzfqbl (myAdmin-test), client 43s15cm8qcgg8an85udt0e087u, no secret
// - PROD pool A: eu-west-1_Hdp40eWmu (myAdmin)
//
// Flask API base URL:
// - TEST host ⇒ local (http://localhost:5000); PRODUCTION host ⇒ Railway
//
// SAM plane current-state delta:
// - Today the SAM plane's only TEST isolation is the `test_` table prefix.
// - No separate TEST stack / TEST API Gateway yet (built in later tasks 19.x-24.x).
//
// Secrets guardrail:
// - All secret values are placeholders here. The frontend never holds a real secret.
