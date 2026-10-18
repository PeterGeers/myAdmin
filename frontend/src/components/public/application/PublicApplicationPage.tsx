/**
 * Container for the PUBLIC member-application form page
 * (spec Members/application-app, task 9.4).
 *
 * Loads a tenant's public field-config via `fetchPublicFieldConfig` (task 9.1) and branches on the
 * discriminated {@link FieldConfigResult} so each arm renders without the page inspecting HTTP
 * status codes:
 *  - `success`      — delegate to the `renderForm` slot (task 9.3 owns the renderer + submit wiring);
 *  - `not_available`— the neutral 409 "not accepting applications yet" state (D15/R5.4);
 *  - `not_found`    — the non-probeable 404 "no such form" state (R1a.4);
 *  - `error`        — a generic failure state.
 *
 * The non-success arms are delegated whole to {@link ApplicationStateMessage} (this task's
 * deliverable), keeping the 409/404/error states in one dedicated component. The `success` arm is
 * a SLOT (`renderForm`) so task 9.3's form + submit path composes here without either task
 * reshaping the other: 9.3 supplies `renderForm`, 9.4 owns everything else.
 *
 * _Requirements: R1a, R1a.4, R5, R5.4, R6b_
 */

import React, { useEffect, useRef, useState } from 'react';
import { Flex, Spinner, VStack } from '@chakra-ui/react';
import {
  fetchPublicFieldConfig,
  type FieldConfigResult,
  type PublicFieldConfig,
} from '../../../services/applicationApi';
import { ApplicationStateMessage } from './ApplicationStateMessage';

export interface PublicApplicationPageProps {
  /** The tenant slug from the public route — carried in the field-config path (D3/D19). */
  tenantSlug: string;
  /**
   * The SUCCESS-arm slot: task 9.3 renders the config-driven form + submit wiring here. Kept a
   * slot so 9.4 (this task) owns the non-form states and 9.3 owns the form without a merge seam.
   */
  renderForm: (config: PublicFieldConfig) => React.ReactNode;
  /** Optional base-URL override (tests inject the MSW base); production resolves fail-fast. */
  baseUrl?: string;
}

/** Loading | the resolved result arm. `null` = still loading the field-config. */
type LoadState = { loading: true } | { loading: false; result: FieldConfigResult };

export const PublicApplicationPage: React.FC<PublicApplicationPageProps> = ({
  tenantSlug,
  renderForm,
  baseUrl,
}) => {
  const [state, setState] = useState<LoadState>({ loading: true });
  // Guard against a state update after unmount / slug change (the fetch is abortable).
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;
    const controller = new AbortController();
    setState({ loading: true });

    fetchPublicFieldConfig(tenantSlug, { baseUrl, signal: controller.signal }).then((result) => {
      // Ignore a deliberate cancel (unmount / slug change) — do not flash an error state.
      if (!activeRef.current) return;
      if (result.status === 'error' && result.message === 'aborted') return;
      setState({ loading: false, result });
    });

    return () => {
      activeRef.current = false;
      controller.abort();
    };
  }, [tenantSlug, baseUrl]);

  if (state.loading) {
    return (
      <Flex data-testid="application-loading" justify="center" py={10}>
        <Spinner />
      </Flex>
    );
  }

  const { result } = state;

  if (result.status === 'success') {
    return <VStack align="stretch">{renderForm(result.data)}</VStack>;
  }

  // Every non-success arm is a non-form state — one dedicated, neutral, bilingual component.
  return <ApplicationStateMessage result={result} />;
};

export default PublicApplicationPage;
