/**
 * PivotBuilderModels Component
 *
 * Saved model management for the PivotBuilder: list, load, save, update, delete.
 *
 * Requirements: 4.1, 4.4, 5.1, 5.2, 5.3, 5.5, 5.6
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §4 PivotBuilder
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Flex,
  HStack,
  IconButton,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  Text,
  useDisclosure,
} from '@chakra-ui/react';
import { DeleteIcon } from '@chakra-ui/icons';
import type { PivotConfig, PivotModelSummary } from '../../types/pivot';
import {
  listPivotModels,
  loadPivotModel,
  savePivotModel,
  updatePivotModel,
  deletePivotModel,
} from '../../services/pivotService';

export interface PivotBuilderModelsProps {
  config: PivotConfig;
  isValid: boolean;
  onLoadModel: (config: PivotConfig) => void;
  t: (key: string, options?: Record<string, any>) => string;
}

export function PivotBuilderModels({
  config,
  isValid,
  onLoadModel,
  t,
}: PivotBuilderModelsProps): React.ReactElement {
  const [models, setModels] = useState<PivotModelSummary[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null);
  const [loadedModelName, setLoadedModelName] = useState<string | null>(null);
  const [modelName, setModelName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const saveModal = useDisclosure();
  const deleteModal = useDisclosure();

  // Load model list on mount
  const refreshModels = useCallback(async () => {
    try {
      const list = await listPivotModels();
      setModels(list);
    } catch (err) {
      console.error('Failed to load pivot models:', err);
    }
  }, []);

  useEffect(() => {
    refreshModels();
  }, [refreshModels]);

  // Handle loading a saved model
  const handleLoadModel = useCallback(
    async (id: number) => {
      setError(null);
      try {
        const model = await loadPivotModel(id);
        setSelectedModelId(id);
        setLoadedModelName(model.name);
        onLoadModel(model.definition);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : t('pivot.errors.loadFailed'),
        );
      }
    },
    [onLoadModel, t],
  );

  // Handle model selection from dropdown
  const handleModelSelect = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const id = e.target.value ? parseInt(e.target.value, 10) : null;
      if (id) {
        handleLoadModel(id);
      } else {
        setSelectedModelId(null);
        setLoadedModelName(null);
      }
    },
    [handleLoadModel],
  );

  // Open save modal
  const handleSaveClick = useCallback(() => {
    setModelName(loadedModelName || '');
    setError(null);
    saveModal.onOpen();
  }, [loadedModelName, saveModal]);

  // Save or update model
  const handleSaveConfirm = useCallback(async () => {
    if (!modelName.trim()) return;
    setError(null);
    setSaving(true);
    try {
      // Check if we're updating an existing model with the same name
      const existingModel = models.find(
        (m) => m.name === modelName.trim() && m.id === selectedModelId,
      );
      if (existingModel) {
        await updatePivotModel(existingModel.id, config);
      } else {
        await savePivotModel(modelName.trim(), config);
      }
      await refreshModels();
      setLoadedModelName(modelName.trim());
      saveModal.onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('pivot.errors.saveFailed');
      // Map known backend errors to translation keys
      if (message.includes('already exists')) {
        setError(t('pivot.models.duplicateName'));
      } else {
        setError(message);
      }
    } finally {
      setSaving(false);
    }
  }, [modelName, models, selectedModelId, config, refreshModels, saveModal, t]);

  // Delete model
  const handleDeleteConfirm = useCallback(async () => {
    if (!selectedModelId) return;
    setError(null);
    setDeleting(true);
    try {
      await deletePivotModel(selectedModelId);
      setSelectedModelId(null);
      setLoadedModelName(null);
      await refreshModels();
      deleteModal.onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('pivot.errors.deleteFailed');
      if (message.includes('not found')) {
        setError(t('pivot.models.notFound'));
      } else {
        setError(message);
      }
    } finally {
      setDeleting(false);
    }
  }, [selectedModelId, refreshModels, deleteModal, t]);

  return (
    <Box>
      {error && (
        <Alert status="error" mb={3} borderRadius="md" size="sm">
          <AlertIcon />
          <Text fontSize="sm">{error}</Text>
        </Alert>
      )}

      <HStack spacing={2} wrap="wrap">
        {/* Model selector dropdown */}
        <Select
          size="sm"
          bg="gray.600"
          color="white"
          value={selectedModelId ?? ''}
          onChange={handleModelSelect}
          placeholder={t('pivot.models.selectModel')}
          maxW="220px"
          aria-label={t('pivot.models.selectModel')}
          sx={{
            '& option': { bg: 'white', color: 'black' },
            '&:not(:placeholder-shown)': { bg: 'orange.500', color: 'white' },
          }}
        >
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.name}
            </option>
          ))}
        </Select>

        {/* Save button */}
        <Button
          size="sm"
          colorScheme="orange"
          variant="outline"
          onClick={handleSaveClick}
          disabled={!isValid}
        >
          {t('pivot.actions.save')}
        </Button>

        {/* Delete button — only when a model is loaded */}
        {selectedModelId && (
          <IconButton
            aria-label={t('pivot.actions.delete')}
            icon={<DeleteIcon />}
            size="sm"
            variant="outline"
            colorScheme="red"
            onClick={deleteModal.onOpen}
          />
        )}
      </HStack>

      {models.length === 0 && (
        <Text fontSize="xs" color="gray.500" mt={1}>
          {t('pivot.models.noModels')}
        </Text>
      )}

      {/* Save Modal */}
      <Modal isOpen={saveModal.isOpen} onClose={saveModal.onClose} size="sm">
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="white">{t('pivot.actions.save')}</ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            {error && (
              <Alert status="error" mb={3} borderRadius="md" size="sm">
                <AlertIcon />
                <Text fontSize="sm">{error}</Text>
              </Alert>
            )}
            <Input
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder={t('pivot.models.enterName')}
              bg="gray.600"
              color="white"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && modelName.trim()) handleSaveConfirm();
              }}
            />
          </ModalBody>
          <ModalFooter>
            <Flex gap={2}>
              <Button variant="ghost" onClick={saveModal.onClose} color="gray.300">
                Cancel
              </Button>
              <Button
                colorScheme="orange"
                onClick={handleSaveConfirm}
                isLoading={saving}
                disabled={!modelName.trim()}
              >
                {t('pivot.actions.save')}
              </Button>
            </Flex>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal isOpen={deleteModal.isOpen} onClose={deleteModal.onClose} size="sm">
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="white">{t('pivot.actions.delete')}</ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            <Text color="gray.300">{t('pivot.models.deleteConfirm')}</Text>
            {loadedModelName && (
              <Text color="white" fontWeight="bold" mt={2}>
                {loadedModelName}
              </Text>
            )}
          </ModalBody>
          <ModalFooter>
            <Flex gap={2}>
              <Button variant="ghost" onClick={deleteModal.onClose} color="gray.300">
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={handleDeleteConfirm}
                isLoading={deleting}
              >
                {t('pivot.actions.delete')}
              </Button>
            </Flex>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
}

export default PivotBuilderModels;
