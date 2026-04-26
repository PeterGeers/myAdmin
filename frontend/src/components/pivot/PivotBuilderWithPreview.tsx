/**
 * PivotBuilderWithPreview
 *
 * Wraps PivotBuilder and PivotResultTable together so that clicking
 * "Execute" shows a live preview of the query results below the builder.
 * Used in the TenantAdmin dashboard's Pivot Views tab.
 */

import React, { useCallback, useState } from 'react';
import { Box, Divider } from '@chakra-ui/react';
import { PivotBuilder } from './PivotBuilder';
import { PivotResultTable } from './PivotResultTable';
import type { PivotConfig, PivotResult } from '../../types/pivot';

export function PivotBuilderWithPreview(): React.ReactElement {
  const [result, setResult] = useState<PivotResult | null>(null);
  const [config, setConfig] = useState<PivotConfig | null>(null);
  const [loading, setLoading] = useState(false);

  const handleResults = useCallback((r: PivotResult) => {
    setResult(r);
    setLoading(false);
  }, []);

  const handleConfigChange = useCallback((c: PivotConfig) => {
    setConfig(c);
  }, []);

  return (
    <Box>
      <PivotBuilder
        onResults={handleResults}
        onConfigChange={handleConfigChange}
      />

      {result && config && (
        <>
          <Divider my={4} borderColor="gray.600" />
          <PivotResultTable
            data={result.data || []}
            columns={result.columns || []}
            config={config}
            isLoading={loading}
          />
        </>
      )}
    </Box>
  );
}

export default PivotBuilderWithPreview;
