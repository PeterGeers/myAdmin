/**
 * Environment_Indicator (Req 5) — on-screen display of the active environment.
 *
 * A derived on-screen label computed from the frontend's resolved `APP_ENV`/config
 * (`src/config/appEnv.ts`). It is shown on the login screen (Req 5.1) and while
 * authenticated with the active pool/identity label (Req 5.2).
 *
 * Non-drift (Req 5.3): the indicator reads `APP_ENV` and `RESOLVED` from the SAME
 * Environment_Resolver that selects the active Cognito pool, so the badge cannot drift
 * from the configuration actually in use. It is NEVER derived from the hostname or any
 * other incidental signal.
 *
 * SAM endpoint (Req 5.4): where the active SAM API endpoint / stack-environment label is
 * observable to the client it is presented alongside the environment label.
 *
 * Visual distinction (Req 5.5): the TEST label is visually distinct from PROD — TEST is a
 * bold amber/orange badge that clearly stands out; PROD is a subtle, neutral grey badge.
 * Distinction never relies on color alone — the literal text "TEST"/"PROD" always conveys
 * the environment, and an `aria-label` names it for assistive technology.
 */

import React from 'react';
import { Badge, HStack, Text, Tooltip } from '@chakra-ui/react';
import { APP_ENV, RESOLVED } from '../config/appEnv';

/** The human-facing short label shown in the badge. */
const ENV_LABEL: Record<typeof APP_ENV, 'TEST' | 'PROD'> =
  { test: 'TEST', production: 'PROD' } as const;

export interface EnvironmentIndicatorProps {
  /**
   * `compact` (default) renders just the TEST/PROD badge — suited to the login screen
   * (Req 5.1). `detailed` additionally renders the active pool/identity label (Req 5.2)
   * and, where observable, the SAM API endpoint / stack label (Req 5.4) — suited to the
   * authenticated layout header.
   */
  variant?: 'compact' | 'detailed';
}

/**
 * Returns true when the resolved SAM API base URL is a concrete, observable endpoint
 * (Req 5.4 — "where observable"). Placeholder values recorded in the Environment_Definition
 * before the TEST/PROD stacks are built are treated as not-yet-observable and suppressed,
 * so the indicator never surfaces a fake endpoint.
 */
function isObservableSamUrl(url: string | undefined): url is string {
  return !!url && !url.includes('PLACEHOLDER');
}

/**
 * On-screen indicator of the active environment, derived entirely from the resolver.
 */
export const EnvironmentIndicator: React.FC<EnvironmentIndicatorProps> = ({
  variant = 'compact',
}) => {
  const isTest = APP_ENV === 'test';
  const label = ENV_LABEL[APP_ENV];
  const poolLabel = RESOLVED.cognito.poolLabel;
  const samUrl = RESOLVED.sam.apiBaseUrl;
  const stackName = RESOLVED.sam.stackName;

  // Req 5.5 — TEST stands out (amber, solid); PROD is subtle/neutral (grey, subtle).
  // Distinction is NOT color-only: the badge text itself ("TEST"/"PROD") conveys it.
  const badge = (
    <Badge
      data-testid="environment-indicator-badge"
      // Stable, color-independent hooks reflecting the resolved environment so the
      // visual distinction (Req 5.5) is assertable without relying on emotion-generated
      // class names (which jsdom does not expose reliably).
      data-env={APP_ENV}
      data-variant={isTest ? 'solid' : 'subtle'}
      colorScheme={isTest ? 'orange' : 'gray'}
      variant={isTest ? 'solid' : 'subtle'}
      fontWeight="bold"
      fontSize="xs"
      px={2}
      py={0.5}
      borderRadius="md"
      letterSpacing="wide"
      // Accessibility: name the environment explicitly, independent of color.
      aria-label={`Active environment: ${label}`}
    >
      {label}
    </Badge>
  );

  if (variant === 'compact') {
    return (
      <HStack
        data-testid="environment-indicator"
        role="status"
        aria-label={`Active environment: ${label}`}
        spacing={2}
        justify="center"
      >
        {badge}
      </HStack>
    );
  }

  // Detailed variant (authenticated layout): badge + pool/identity label (Req 5.2) and,
  // where observable, the SAM API endpoint / stack label (Req 5.4).
  const samLabel = isObservableSamUrl(samUrl) ? samUrl : stackName;

  return (
    <HStack
      data-testid="environment-indicator"
      role="status"
      aria-label={`Active environment: ${label}, pool ${poolLabel}`}
      spacing={2}
      flexShrink={0}
    >
      {badge}
      <Text
        data-testid="environment-indicator-pool"
        fontSize="xs"
        color={isTest ? 'orange.200' : 'gray.400'}
        noOfLines={1}
      >
        {poolLabel}
      </Text>
      <Tooltip label={`SAM: ${samLabel}`} openDelay={300}>
        <Text
          data-testid="environment-indicator-sam"
          fontSize="xs"
          color="gray.500"
          display={{ base: 'none', md: 'inline' }}
          maxW="220px"
          noOfLines={1}
        >
          {samLabel}
        </Text>
      </Tooltip>
    </HStack>
  );
};

export default EnvironmentIndicator;
