# myAdmin Frontend

React TypeScript frontend for the myAdmin financial administration platform, built with Vite.

## Tech Stack

- **Framework**: React 19 with TypeScript 5.9+
- **Build Tool**: Vite 8.x
- **UI**: Chakra UI 2.8, Material UI 7.3, Framer Motion
- **Charts**: Recharts 3.3, Plotly.js (lazy-loaded)
- **Auth**: AWS Amplify 6 (Cognito)
- **Testing**: Vitest, Playwright, React Testing Library, fast-check
- **Linting**: ESLint flat config (`eslint.config.js`)

## Getting Started

```bash
# Install dependencies
npm install

# Start dev server (port 3000)
npm start

# Run unit tests
npm run test:run

# Run tests in watch mode
npm test

# Run e2e tests (requires backend running)
npm run test:e2e

# Lint
npm run lint

# Production build
npm run build

# Preview production build locally
npm run preview
```

## Environment Variables

Copy `.env.example` to `.env` and fill in the values. All frontend env vars use the `VITE_` prefix:

| Variable                    | Description              |
| --------------------------- | ------------------------ |
| `VITE_COGNITO_USER_POOL_ID` | AWS Cognito User Pool ID |
| `VITE_COGNITO_CLIENT_ID`    | Cognito App Client ID    |
| `VITE_COGNITO_DOMAIN`       | Cognito domain           |
| `VITE_AWS_REGION`           | AWS region               |
| `VITE_API_URL`              | Backend API URL          |
| `VITE_REDIRECT_SIGN_IN`     | OAuth sign-in redirect   |
| `VITE_REDIRECT_SIGN_OUT`    | OAuth sign-out redirect  |
| `VITE_DOCS_URL`             | Documentation URL        |

## Project Structure

```
frontend/
├── src/
│   ├── components/       # Reusable UI components
│   ├── pages/            # Page-level components
│   ├── services/         # API service layer
│   ├── hooks/            # Custom React hooks
│   ├── context/          # React context providers
│   ├── types/            # TypeScript type definitions
│   └── utils/            # Utility functions
├── tests/                # E2E tests (Playwright)
├── vite.config.ts        # Vite + Vitest configuration
├── eslint.config.js      # ESLint flat config
└── tsconfig.json         # TypeScript configuration
```

## Build & Deploy

```bash
# Production build (outputs to build/)
npm run build

# Deploy to GitHub Pages
npm run deploy

# Bundle analysis
ANALYZE=true npm run build
```

The production build uses `base: '/myAdmin'` for GitHub Pages deployment. Asset paths are prefixed accordingly.
