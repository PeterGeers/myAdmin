/**
 * Template Preview Component
 * 
 * Displays template preview in a sandboxed iframe with sample data.
 * Includes loading skeleton and informational note.
 */

import React from 'react';
import {
  Box,
  VStack,
  Text,
  Skeleton,
  Alert,
  AlertIcon,
  AlertDescription,
} from '@chakra-ui/react';

/**
 * Component props
 */
interface TemplatePreviewProps {
  previewHtml: string;
  loading?: boolean;
  sampleDataInfo?: {
    source: string;
    record_count?: number;
  } | null;
}

/**
 * TemplatePreview Component
 */
export const TemplatePreview: React.FC<TemplatePreviewProps> = ({
  previewHtml,
  loading = false,
  sampleDataInfo = null,
}) => {
  return (
    <VStack spacing={4} align="stretch" h="100%">
      {/* Preview Note */}
      <Alert status="info" bg="blue.900" borderRadius="md">
        <AlertIcon />
        <AlertDescription fontSize="sm">
          This shows how your template will look with sample data
          {sampleDataInfo && sampleDataInfo.source === 'database' && (
            <Text as="span" ml={1}>
              (loaded from {sampleDataInfo.source}
              {sampleDataInfo.record_count && ` - ${sampleDataInfo.record_count} record(s)`})
            </Text>
          )}
          {sampleDataInfo && sampleDataInfo.source === 'placeholder' && (
            <Text as="span" ml={1}>
              (using placeholder data - no real data available)
            </Text>
          )}
        </AlertDescription>
      </Alert>

      {/* Loading Skeleton */}
      {loading && (
        <VStack spacing={3} align="stretch">
          <Skeleton height="40px" borderRadius="md" />
          <Skeleton height="200px" borderRadius="md" />
          <Skeleton height="150px" borderRadius="md" />
          <Skeleton height="100px" borderRadius="md" />
        </VStack>
      )}

      {/* Preview Iframe */}
      {!loading && previewHtml && (
        <Box
          flex={1}
          position="relative"
          minH="600px"
          border="1px solid"
          borderColor="gray.700"
          borderRadius="md"
          overflow="hidden"
          bg="white"
        >
          <Box
            as="iframe"
            title="Template Preview"
            srcDoc={previewHtml}
            sandbox=""
            w="100%"
            h="100%"
            border="none"
            position="absolute"
            top={0}
            left={0}
            right={0}
            bottom={0}
          />
        </Box>
      )}

      {/* No Preview Message */}
      {!loading && !previewHtml && (
        <Box
          flex={1}
          minH="600px"
          border="2px dashed"
          borderColor="gray.700"
          borderRadius="md"
          display="flex"
          alignItems="center"
          justifyContent="center"
          bg="gray.800"
        >
          <VStack spacing={2}>
            <Text fontSize="lg" color="gray.500">
              No preview available
            </Text>
            <Text fontSize="sm" color="gray.600">
              Upload a template to see the preview
            </Text>
          </VStack>
        </Box>
      )}

      {/* Security Note */}
      <Alert status="warning" bg="yellow.900" borderRadius="md" size="sm">
        <AlertIcon />
        <AlertDescription fontSize="xs">
          <strong>Security:</strong> Preview is displayed in a sandboxed iframe with scripts disabled.
          No JavaScript will execute from the template.
        </AlertDescription>
      </Alert>
    </VStack>
  );
};

export default TemplatePreview;
