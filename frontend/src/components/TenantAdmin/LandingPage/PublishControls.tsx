/**
 * PublishControls — Publish/unpublish buttons + version history with rollback.
 *
 * Task 4.3: Shows current published version, publish/unpublish actions,
 * version history list fetched from GET /api/landing/versions,
 * and a rollback button per version entry.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, Divider,
  useToast, Spinner, IconButton, Tooltip,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay,
} from '@chakra-ui/react';
import { RepeatIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import {
  publishLandingPage,
  unpublishLandingPage,
  getVersions,
  rollbackToVersion,
  VersionEntry,
} from '../../../services/landingPageApi';

interface PublishControlsProps {
  currentVersion: number;
  onVersionChange: (version: number) => void;
  sectionsCount: number;
}

export default function PublishControls({
  currentVersion,
  onVersionChange,
  sectionsCount,
}: PublishControlsProps) {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  const [publishing, setPublishing] = useState(false);
  const [unpublishing, setUnpublishing] = useState(false);
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [rollingBack, setRollingBack] = useState<number | null>(null);

  // Rollback confirmation dialog
  const [rollbackTarget, setRollbackTarget] = useState<number | null>(null);
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  const loadVersions = useCallback(async () => {
    setLoadingVersions(true);
    try {
      const data = await getVersions();
      setVersions(data);
    } catch {
      // Silent fail — versions are informational
    } finally {
      setLoadingVersions(false);
    }
  }, []);

  useEffect(() => {
    loadVersions();
  }, [loadVersions]);

  const handlePublish = async () => {
    setPublishing(true);
    try {
      const result = await publishLandingPage();
      if (result.success) {
        onVersionChange(result.version);
        toast({
          title: 'Published',
          description: `Version ${result.version} is now live at ${result.public_url}`,
          status: 'success',
          duration: 5000,
        });
        // Refresh version list
        loadVersions();
      }
    } catch (err) {
      toast({
        title: 'Publish failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setPublishing(false);
    }
  };

  const handleUnpublish = async () => {
    setUnpublishing(true);
    try {
      const result = await unpublishLandingPage();
      if (result.success) {
        toast({
          title: 'Unpublished',
          description: 'Landing page is now offline',
          status: 'info',
          duration: 3000,
        });
      }
    } catch (err) {
      toast({
        title: 'Unpublish failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setUnpublishing(false);
    }
  };

  const handleRollback = async () => {
    if (!rollbackTarget) return;
    setRollingBack(rollbackTarget);
    setRollbackTarget(null);

    try {
      const result = await rollbackToVersion(rollingBack!);
      if (result.success) {
        onVersionChange(result.version);
        toast({
          title: 'Rollback successful',
          description: `Restored and published version ${rollingBack}`,
          status: 'success',
          duration: 5000,
        });
        loadVersions();
      }
    } catch (err) {
      toast({
        title: 'Rollback failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setRollingBack(null);
    }
  };

  const formatDate = (isoDate: string): string => {
    try {
      return new Date(isoDate).toLocaleString('nl-NL', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoDate;
    }
  };

  return (
    <Box bg="gray.800" borderRadius="md" p={4}>
      {/* Current version + actions */}
      <VStack align="stretch" spacing={3}>
        <HStack justify="space-between">
          <Text color="gray.300" fontSize="sm" fontWeight="semibold">
            Publish Controls
          </Text>
          {currentVersion > 0 && (
            <Badge colorScheme="green" fontSize="xs">
              v{currentVersion}
            </Badge>
          )}
        </HStack>

        <HStack spacing={2}>
          <Button
            size="sm"
            colorScheme="green"
            isLoading={publishing}
            onClick={handlePublish}
            isDisabled={sectionsCount === 0}
            flex="1"
          >
            Publish
          </Button>
          <Button
            size="sm"
            variant="ghost"
            colorScheme="red"
            isLoading={unpublishing}
            onClick={handleUnpublish}
            flex="1"
          >
            Unpublish
          </Button>
        </HStack>

        {/* Version History */}
        <Divider borderColor="gray.600" />

        <HStack justify="space-between">
          <Text color="gray.400" fontSize="xs" fontWeight="semibold">
            Version History
          </Text>
          <Tooltip label="Refresh">
            <IconButton
              aria-label="Refresh versions"
              icon={<RepeatIcon />}
              size="xs"
              variant="ghost"
              color="gray.400"
              onClick={loadVersions}
              isLoading={loadingVersions}
            />
          </Tooltip>
        </HStack>

        {loadingVersions && versions.length === 0 ? (
          <Spinner size="sm" color="gray.400" />
        ) : versions.length === 0 ? (
          <Text color="gray.500" fontSize="xs">
            No published versions yet
          </Text>
        ) : (
          <VStack align="stretch" spacing={1} maxH="200px" overflowY="auto">
            {versions.map((v) => (
              <HStack
                key={v.version}
                justify="space-between"
                bg="gray.700"
                px={3}
                py={2}
                borderRadius="sm"
                fontSize="xs"
              >
                <Box>
                  <Text color="gray.200" fontWeight="medium">
                    v{v.version}
                  </Text>
                  <Text color="gray.400" fontSize="2xs">
                    {formatDate(v.published_at)}
                  </Text>
                </Box>
                <Tooltip label={`Rollback to v${v.version}`}>
                  <IconButton
                    aria-label={`Rollback to version ${v.version}`}
                    icon={<RepeatIcon />}
                    size="xs"
                    variant="ghost"
                    colorScheme="orange"
                    isLoading={rollingBack === v.version}
                    onClick={() => setRollbackTarget(v.version)}
                  />
                </Tooltip>
              </HStack>
            ))}
          </VStack>
        )}
      </VStack>

      {/* Rollback confirmation dialog */}
      <AlertDialog
        isOpen={rollbackTarget !== null}
        leastDestructiveRef={cancelRef}
        onClose={() => setRollbackTarget(null)}
      >
        <AlertDialogContent bg="gray.800" color="white">
          <AlertDialogHeader fontSize="lg" fontWeight="bold">
            Rollback to version {rollbackTarget}?
          </AlertDialogHeader>
          <AlertDialogBody>
            This will restore version {rollbackTarget} as the current draft and
            immediately re-publish it. The current draft will be overwritten.
          </AlertDialogBody>
          <AlertDialogFooter>
            <Button ref={cancelRef} onClick={() => setRollbackTarget(null)} variant="ghost">
              Cancel
            </Button>
            <Button colorScheme="orange" onClick={handleRollback} ml={3}>
              Rollback & Publish
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Box>
  );
}
