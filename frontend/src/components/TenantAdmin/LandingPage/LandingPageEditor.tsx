/**
 * LandingPageEditor — Main CMS block editor for the tenant landing page.
 *
 * Manages the sections array, provides block reordering (drag-and-drop),
 * add/remove blocks, per-block editing, and auto-saves via debounced PUT.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, ButtonGroup, Text, Spinner, useToast,
  Alert, AlertIcon, Badge, Tooltip,
} from '@chakra-ui/react';
import { AddIcon, ViewIcon, EditIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { getDraft, saveDraft, publishLandingPage, unpublishLandingPage, getSlug, setSlug, validateSlug, Section } from '../../../services/landingPageApi';
import BlockListItem from './BlockListItem';
import AddBlockModal from './AddBlockModal';
import BlockConfigurator from './BlockConfigurator';
import PreviewPanel from './PreviewPanel';
import BrandingSettings from './BrandingSettings';
import SeoSettings from './SeoSettings';
import DomainSettings from './DomainSettings';
import PublishControls from './PublishControls';

interface LandingPageEditorProps {
  tenant: string;
  tenantModules: string[];
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export default function LandingPageEditor({ tenant, tenantModules }: LandingPageEditorProps) {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  // Slug state
  const [slug, setSlugState] = useState<string | null>(null);
  const [slugInput, setSlugInput] = useState('');
  const [slugError, setSlugError] = useState<string | null>(null);
  const [slugSaving, setSlugSaving] = useState(false);
  const [needsSlug, setNeedsSlug] = useState(false);

  // Core state
  const [sections, setSections] = useState<Section[]>([]);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // UI state
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [publishing, setPublishing] = useState(false);
  const [addBlockOpen, setAddBlockOpen] = useState(false);
  const [editingBlockId, setEditingBlockId] = useState<string | null>(null);
  const [view, setView] = useState<'blocks-edit' | 'blocks-preview' | 'branding' | 'seo' | 'versions' | 'domains'>('blocks-edit');

  // Auto-save refs
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sectionsRef = useRef<Section[]>(sections);
  const hasChangesRef = useRef(false);

  // Keep ref in sync
  useEffect(() => {
    sectionsRef.current = sections;
  }, [sections]);

  // Load slug + draft on mount
  useEffect(() => {
    loadSlugAndDraft();
    return () => {
      // Flush pending save on unmount
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        if (hasChangesRef.current) {
          saveDraft(sectionsRef.current).catch(() => {});
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  const loadSlugAndDraft = async () => {
    setLoading(true);
    setError(null);
    setNeedsSlug(false);
    try {
      const slugResp = await getSlug();
      if (slugResp.success && slugResp.data.slug) {
        setSlugState(slugResp.data.slug);
        // Slug exists, load draft
        await loadDraft();
      } else {
        // No slug configured
        setNeedsSlug(true);
        setLoading(false);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      if (msg.includes('No slug') || msg.includes('slug')) {
        setNeedsSlug(true);
      } else {
        setError(msg);
      }
      setLoading(false);
    }
  };

  const handleSaveSlug = async () => {
    setSlugError(null);
    setSlugSaving(true);
    try {
      // Validate first
      const valResp = await validateSlug(slugInput);
      if (!valResp.valid) {
        setSlugError(valResp.error || 'Invalid slug');
        setSlugSaving(false);
        return;
      }
      // Save slug
      const resp = await setSlug(slugInput);
      if (resp.success) {
        setSlugState(slugInput);
        setNeedsSlug(false);
        // Now load the draft
        await loadDraft();
      } else {
        setSlugError(resp.error || 'Failed to save slug');
      }
    } catch (err) {
      setSlugError(err instanceof Error ? err.message : 'Failed to save slug');
    } finally {
      setSlugSaving(false);
    }
  };

  const loadDraft = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await getDraft();
      if (response.success && response.data) {
        setSections(response.data.sections || []);
        setVersion(response.data.version || 0);
      } else {
        // No draft yet — start with empty sections
        setSections([]);
        setVersion(0);
      }
    } catch (err) {
      // 404 or "no draft" = no draft yet, that's fine — start empty
      const msg = err instanceof Error ? err.message : 'Unknown error';
      if (msg.includes('404') || msg.includes('No draft') || msg.includes('no draft')) {
        setSections([]);
        setVersion(0);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  // Debounced auto-save (2 seconds)
  const triggerAutoSave = useCallback(() => {
    hasChangesRef.current = true;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      setSaveStatus('saving');
      try {
        const result = await saveDraft(sectionsRef.current);
        if (result.success) {
          setVersion(result.version);
          setSaveStatus('saved');
          hasChangesRef.current = false;
          // Reset to idle after 3s
          setTimeout(() => setSaveStatus('idle'), 3000);
        } else {
          setSaveStatus('error');
        }
      } catch {
        setSaveStatus('error');
      }
    }, 2000);
  }, []);

  // --- Section manipulation ---

  const updateSections = (newSections: Section[]) => {
    setSections(newSections);
    triggerAutoSave();
  };

  const handleReorder = (fromIndex: number, toIndex: number) => {
    const updated = [...sections];
    const [moved] = updated.splice(fromIndex, 1);
    updated.splice(toIndex, 0, moved);
    updateSections(updated);
  };

  const handleAddBlock = (type: string, layout: string) => {
    const newSection: Section = {
      id: `block-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      type,
      layout,
      properties: getDefaultProperties(type),
    };
    updateSections([...sections, newSection]);
    setAddBlockOpen(false);
    // Open configurator for the new block
    setEditingBlockId(newSection.id);
  };

  const handleRemoveBlock = (blockId: string) => {
    updateSections(sections.filter(s => s.id !== blockId));
    if (editingBlockId === blockId) setEditingBlockId(null);
  };

  const handleUpdateBlock = (blockId: string, updates: Partial<Section>) => {
    updateSections(sections.map(s => s.id === blockId ? { ...s, ...updates } : s));
  };

  // --- Publish / Unpublish ---

  const handlePublish = async () => {
    setPublishing(true);
    try {
      // Flush pending auto-save first
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        if (hasChangesRef.current) {
          await saveDraft(sectionsRef.current);
          hasChangesRef.current = false;
        }
      }
      const result = await publishLandingPage();
      if (result.success) {
        setVersion(result.version);
        toast({
          title: t('landingPage.editor.published'),
          description: result.public_url,
          status: 'success',
          duration: 5000,
        });
      }
    } catch (err) {
      toast({
        title: t('landingPage.editor.publishError'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setPublishing(false);
    }
  };

  const handleUnpublish = async () => {
    try {
      const result = await unpublishLandingPage();
      if (result.success) {
        toast({
          title: t('landingPage.editor.unpublished'),
          status: 'info',
          duration: 3000,
        });
      }
    } catch (err) {
      toast({
        title: t('landingPage.editor.unpublishError'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    }
  };

  // --- Render ---

  if (loading) {
    return (
      <Box display="flex" alignItems="center" justifyContent="center" minH="200px">
        <Spinner size="lg" color="orange.400" />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert status="error" bg="red.900" borderRadius="md">
        <AlertIcon />
        <Text color="white">{error}</Text>
        <Button ml="auto" size="sm" onClick={loadSlugAndDraft}>Retry</Button>
      </Alert>
    );
  }

  if (needsSlug) {
    return (
      <Box maxW="500px" p={6} bg="gray.800" borderRadius="md">
        <VStack spacing={4} align="stretch">
          <Text color="white" fontWeight="bold" fontSize="lg">
            {t('landingPage.editor.setupSlug')}
          </Text>
          <Text color="gray.300" fontSize="sm">
            {t('landingPage.editor.slugDescription')}
          </Text>
          <HStack>
            <Box
              as="input"
              flex={1}
              px={3}
              py={2}
              bg="gray.700"
              color="white"
              borderRadius="md"
              border="1px solid"
              borderColor={slugError ? 'red.400' : 'gray.600'}
              placeholder="my-company"
              value={slugInput}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                setSlugInput(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''));
                setSlugError(null);
              }}
              _focus={{ borderColor: 'orange.400', outline: 'none' }}
            />
            <Button
              colorScheme="orange"
              size="md"
              onClick={handleSaveSlug}
              isLoading={slugSaving}
              isDisabled={slugInput.length < 3}
            >
              {t('landingPage.editor.saveSlug')}
            </Button>
          </HStack>
          {slugError && (
            <Text color="red.300" fontSize="sm">{slugError}</Text>
          )}
          <Text color="gray.500" fontSize="xs">
            {t('landingPage.editor.slugHint')}
          </Text>
        </VStack>
      </Box>
    );
  }

  const editingBlock = editingBlockId ? sections.find(s => s.id === editingBlockId) : null;

  return (
    <Box>
      {/* Toolbar — single row */}
      <HStack justify="space-between" mb={4} flexWrap="wrap" gap={2}>
        <HStack spacing={3}>
          <ButtonGroup size="sm" isAttached>
            <Button
              colorScheme="orange"
              leftIcon={<EditIcon />}
              opacity={view === 'blocks-edit' ? 1 : 0.7}
              onClick={() => setView('blocks-edit')}
            >
              Edit
            </Button>
            <Button
              colorScheme="orange"
              leftIcon={<ViewIcon />}
              opacity={view === 'blocks-preview' ? 1 : 0.7}
              onClick={() => setView('blocks-preview')}
            >
              Preview
            </Button>
            <Button
              colorScheme="orange"
              opacity={view === 'branding' ? 1 : 0.7}
              onClick={() => setView('branding')}
            >
              Branding
            </Button>
            <Button
              colorScheme="orange"
              opacity={view === 'seo' ? 1 : 0.7}
              onClick={() => setView('seo')}
            >
              SEO
            </Button>
            <Button
              colorScheme="orange"
              opacity={view === 'versions' ? 1 : 0.7}
              onClick={() => setView('versions')}
            >
              Versions
            </Button>
            <Button
              colorScheme="orange"
              opacity={view === 'domains' ? 1 : 0.7}
              onClick={() => setView('domains')}
            >
              Domains
            </Button>
          </ButtonGroup>

          {view === 'blocks-edit' && (
            <Tooltip label={t('landingPage.tooltips.addBlock')} placement="bottom" hasArrow>
              <Button
                leftIcon={<AddIcon />}
                size="sm"
                colorScheme="orange"
                onClick={() => setAddBlockOpen(true)}
              >
                {t('landingPage.editor.addBlock')}
              </Button>
            </Tooltip>
          )}

          <SaveStatusBadge status={saveStatus} />
        </HStack>

        <HStack spacing={2}>
          {version > 0 && (
            <Badge colorScheme="gray" fontSize="xs">v{version}</Badge>
          )}
          <Tooltip label={t('landingPage.editor.unpublishTooltip')}>
            <Button size="sm" variant="ghost" colorScheme="red" onClick={handleUnpublish}>
              {t('landingPage.editor.unpublish')}
            </Button>
          </Tooltip>
          <Tooltip label={t('landingPage.tooltips.publish')} placement="bottom" hasArrow>
            <Button
              size="sm"
              colorScheme="green"
              isLoading={publishing}
              onClick={handlePublish}
              isDisabled={sections.length === 0}
            >
              {t('landingPage.editor.publish')}
            </Button>
          </Tooltip>
        </HStack>
      </HStack>

      {/* Content area */}
      {view === 'blocks-edit' && (
        <HStack align="start" spacing={4}>
          <VStack flex="1" spacing={2} align="stretch" minW="0">
            {sections.length === 0 ? (
              <Box
                p={8}
                textAlign="center"
                bg="gray.800"
                borderRadius="md"
                border="2px dashed"
                borderColor="gray.600"
              >
                <Text color="gray.400" mb={3}>{t('landingPage.editor.emptyState')}</Text>
                <Button
                  leftIcon={<AddIcon />}
                  size="sm"
                  colorScheme="orange"
                  variant="outline"
                  onClick={() => setAddBlockOpen(true)}
                >
                  {t('landingPage.editor.addFirstBlock')}
                </Button>
              </Box>
            ) : (
              sections.map((section, index) => (
                <BlockListItem
                  key={section.id}
                  section={section}
                  index={index}
                  totalCount={sections.length}
                  isEditing={editingBlockId === section.id}
                  onEdit={() => setEditingBlockId(section.id)}
                  onRemove={() => handleRemoveBlock(section.id)}
                  onReorder={handleReorder}
                />
              ))
            )}
          </VStack>

          {editingBlock && (
            <Box w="380px" flexShrink={0}>
              <BlockConfigurator
                section={editingBlock}
                onUpdate={(updates) => handleUpdateBlock(editingBlock.id, updates)}
                onClose={() => setEditingBlockId(null)}
              />
            </Box>
          )}
        </HStack>
      )}

      {view === 'blocks-preview' && (
        <PreviewPanel sections={sections} />
      )}

      {view === 'branding' && (
        <Box color="white">
          <BrandingSettings />
        </Box>
      )}

      {view === 'seo' && (
        <Box color="white">
          <SeoSettings />
        </Box>
      )}

      {view === 'versions' && (
        <Box maxW="500px">
          <PublishControls
            onVersionChange={(newVersion) => {
              setVersion(newVersion);
              // Reload the draft after rollback to reflect restored sections
              loadDraft();
            }}
          />
        </Box>
      )}

      {view === 'domains' && (
        <Box maxW="600px">
          <DomainSettings />
        </Box>
      )}

      {/* Add Block Modal */}
      <AddBlockModal
        isOpen={addBlockOpen}
        onClose={() => setAddBlockOpen(false)}
        onAdd={handleAddBlock}
        tenantModules={tenantModules}
      />
    </Box>
  );
}

// --- Helper components ---

function SaveStatusBadge({ status }: { status: SaveStatus }) {
  const { t } = useTypedTranslation('admin');
  switch (status) {
    case 'saving':
      return <Badge colorScheme="yellow" fontSize="xs">💾 {t('landingPage.editor.saving')}</Badge>;
    case 'saved':
      return <Badge colorScheme="green" fontSize="xs">✓ {t('landingPage.editor.saved')}</Badge>;
    case 'error':
      return <Badge colorScheme="red" fontSize="xs">⚠ {t('landingPage.editor.saveError')}</Badge>;
    default:
      return null;
  }
}

// --- Default properties per block type ---

function getDefaultProperties(type: string): Record<string, unknown> {
  switch (type) {
    case 'hero':
      return { title: '', subtitle: '', cta_text: '', cta_url: '', image_key: '' };
    case 'about':
      return { content_md: '', image_key: '' };
    case 'gallery':
      return { images: [] };
    case 'testimonials':
      return { items: [] };
    case 'faq':
      return { items: [] };
    case 'pricing':
      return { items: [] };
    case 'cta':
      return { title: '', subtitle: '', button_text: '', button_url: '' };
    case 'embed':
      return { url: '', height: '500px', title: '' };
    case 'contact':
      return { title: '', subtitle: '' };
    case 'services':
      return {};
    default:
      return {};
  }
}
