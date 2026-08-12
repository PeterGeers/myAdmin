/**
 * BrandingSettings — Logo, colors, tagline, contact info, and social media links.
 *
 * Allows the tenant admin to configure branding details and social media profiles
 * that appear on the published landing page (footer, header, SEO).
 *
 * Tasks 3.15 + 3.16
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, VStack, HStack, Text, FormControl, FormLabel, Input, Button,
  Divider, Icon, InputGroup, InputLeftElement, useToast, Spinner,
  FormErrorMessage, SimpleGrid, Switch,
} from '@chakra-ui/react';
import {
  FaInstagram, FaFacebook, FaAirbnb, FaLinkedin, FaYoutube,
  FaTiktok, FaXTwitter, FaHotel,
} from 'react-icons/fa6';
import type { IconType } from 'react-icons';
import ImageUploader from './ImageUploader';
import ThemeSelector from './ThemeSelector';
import TypographySettings from './TypographySettings';
import { THEME_PRESETS } from './themePresets';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import {
  getBrandingSettings, saveBrandingSettings,
  SocialLinks, LandingPageSettings,
} from '../../../services/landingPageApi';

// ============================================================================
// Types & Constants
// ============================================================================

interface SocialPlatform {
  key: keyof SocialLinks;
  icon: IconType;
  label: string;
  placeholder: string;
}

const SOCIAL_PLATFORMS: SocialPlatform[] = [
  { key: 'instagram', icon: FaInstagram, label: 'Instagram', placeholder: 'https://instagram.com/...' },
  { key: 'facebook', icon: FaFacebook, label: 'Facebook', placeholder: 'https://facebook.com/...' },
  { key: 'airbnb', icon: FaAirbnb, label: 'Airbnb', placeholder: 'https://airbnb.com/...' },
  { key: 'booking_com', icon: FaHotel, label: 'Booking.com', placeholder: 'https://booking.com/...' },
  { key: 'linkedin', icon: FaLinkedin, label: 'LinkedIn', placeholder: 'https://linkedin.com/...' },
  { key: 'youtube', icon: FaYoutube, label: 'YouTube', placeholder: 'https://youtube.com/...' },
  { key: 'tiktok', icon: FaTiktok, label: 'TikTok', placeholder: 'https://tiktok.com/...' },
  { key: 'twitter_x', icon: FaXTwitter, label: 'X (Twitter)', placeholder: 'https://x.com/...' },
];

// ============================================================================
// Component
// ============================================================================

export default function BrandingSettings() {
  const { t } = useTypedTranslation('admin');
  const toast = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<LandingPageSettings>({
    company_name: '',
    tagline: '',
    logo_url: '',
    color_primary: '#2D5F8A',
    color_accent: '#F4A261',
    address: '',
    postal_city: '',
    country: '',
    phone: '',
    email: '',
    coc: '',
    vat: '',
    seo_title: '',
    seo_description: '',
    og_image_url: '',
    social_links: {},
    show_share_buttons: false,
    font_heading: 'system',
    font_body: 'system',
    base_spacing: 'normal',
    border_radius_global: 'rounded',
    shadow_style: 'subtle',
  });
  const [socialErrors, setSocialErrors] = useState<Record<string, string>>({});

  // Theme preset state (Tasks 37–39)
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [themeOverrides, setThemeOverrides] = useState<Record<string, string>>({});
  // Ref to suppress override tracking when a theme is being applied programmatically
  const applyingThemeRef = useRef(false);

  // Load settings
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await getBrandingSettings();
      setSettings(data);
      // Initialize theme state from loaded settings (Task 41)
      if (data.theme) {
        setSelectedPreset(data.theme.preset ?? null);
        setThemeOverrides(data.theme.overrides ?? {});
      }
    } catch {
      // If 404 or no settings yet, use defaults
    } finally {
      setLoading(false);
    }
  };

  // Field updater — tracks overrides when a theme is active (Task 37)
  const updateField = useCallback((field: keyof LandingPageSettings, value: string | boolean) => {
    setSettings(prev => ({ ...prev, [field]: value }));

    // Track overrides: if a theme is selected and this is a theme-managed field,
    // record the manual change as an override (unless we're programmatically applying a theme)
    if (!applyingThemeRef.current && selectedPreset !== null) {
      const themeFields = ['color_primary', 'color_accent'];
      if (themeFields.includes(field as string)) {
        setThemeOverrides(prev => ({ ...prev, [field]: value as string }));
      }
    }
  }, [selectedPreset]);

  // Theme selection handler (Task 37)
  const handleSelectTheme = useCallback((presetId: string | null) => {
    setSelectedPreset(presetId);
    setThemeOverrides({});

    if (presetId === null) {
      // Custom mode — don't change field values (Task 38)
      return;
    }

    // Find the preset and fill colour fields
    const preset = THEME_PRESETS.find(p => p.id === presetId);
    if (preset) {
      applyingThemeRef.current = true;
      setSettings(prev => ({
        ...prev,
        color_primary: preset.color_primary,
        color_accent: preset.color_accent,
      }));
      applyingThemeRef.current = false;
    }
  }, []);

  // Reset to theme defaults (Task 39)
  const handleResetTheme = useCallback(() => {
    if (selectedPreset === null) return;

    const preset = THEME_PRESETS.find(p => p.id === selectedPreset);
    if (preset) {
      applyingThemeRef.current = true;
      setSettings(prev => ({
        ...prev,
        color_primary: preset.color_primary,
        color_accent: preset.color_accent,
      }));
      setThemeOverrides({});
      applyingThemeRef.current = false;
    }
  }, [selectedPreset]);

  // Social link updater with validation
  const updateSocialLink = useCallback((platform: keyof SocialLinks, value: string) => {
    setSettings(prev => ({
      ...prev,
      social_links: { ...prev.social_links, [platform]: value },
    }));

    // Validate: empty is fine, otherwise must start with https://
    if (value && !value.startsWith('https://')) {
      setSocialErrors(prev => ({ ...prev, [platform]: t('landingPage.branding.socialUrlError') }));
    } else {
      setSocialErrors(prev => {
        const next = { ...prev };
        delete next[platform];
        return next;
      });
    }
  }, [t]);

  // Save handler
  const handleSave = async () => {
    // Check for social link validation errors
    if (Object.keys(socialErrors).length > 0) {
      toast({
        title: t('landingPage.branding.fixErrors'),
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setSaving(true);
    try {
      // Only send non-empty social links
      const cleanedSocialLinks: SocialLinks = {};
      for (const [key, value] of Object.entries(settings.social_links)) {
        if (value && value.trim()) {
          cleanedSocialLinks[key as keyof SocialLinks] = value.trim();
        }
      }

      await saveBrandingSettings({
        ...settings,
        social_links: cleanedSocialLinks,
        theme: {
          preset: selectedPreset,
          overrides: themeOverrides,
        },
      });

      toast({
        title: t('landingPage.branding.saved'),
        status: 'success',
        duration: 3000,
      });
    } catch (err) {
      toast({
        title: t('landingPage.branding.saveError'),
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" alignItems="center" justifyContent="center" minH="200px">
        <Spinner size="lg" color="orange.400" />
      </Box>
    );
  }

  return (
    <VStack spacing={6} align="stretch" color="gray.100">
      {/* Save button — top right */}
      <HStack justify="flex-end">
        <Button
          colorScheme="orange"
          size="sm"
          onClick={handleSave}
          isLoading={saving}
        >
          {t('landingPage.branding.save')}
        </Button>
      </HStack>

      {/* Company & Branding */}
      <SectionHeading title={t('landingPage.branding.companyInfo')} />
      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        <BrandingField
          label={t('landingPage.branding.companyName')}
          value={settings.company_name}
          onChange={(v) => updateField('company_name', v)}
        />
        <BrandingField
          label={t('landingPage.branding.tagline')}
          value={settings.tagline}
          onChange={(v) => updateField('tagline', v)}
        />
      </SimpleGrid>
      <ImageUploader
        label={t('landingPage.branding.logoUrl')}
        currentImageKey={settings.logo_url}
        onUpload={(imageKey) => updateField('logo_url', imageKey)}
      />

      {/* Theme Selector — Task 36 */}
      <ThemeSelector
        selectedPreset={selectedPreset}
        onSelectTheme={handleSelectTheme}
        onReset={handleResetTheme}
      />

      <Divider borderColor="gray.600" />

      {/* Colors */}
      <SectionHeading title={t('landingPage.branding.colors')} />
      <HStack spacing={4}>
        <FormControl>
          <FormLabel color="gray.300" fontSize="xs">{t('landingPage.branding.primaryColor')}</FormLabel>
          <HStack>
            <Input
              type="color"
              value={settings.color_primary}
              onChange={(e) => updateField('color_primary', e.target.value)}
              w="50px"
              h="36px"
              p={0}
              border="none"
              cursor="pointer"
            />
            <Input
              size="sm"
              bg="gray.700"
              color="white"
              borderColor="gray.600"
              value={settings.color_primary}
              onChange={(e) => updateField('color_primary', e.target.value)}
              placeholder="#2D5F8A"
              maxW="120px"
            />
          </HStack>
        </FormControl>
        <FormControl>
          <FormLabel color="gray.300" fontSize="xs">{t('landingPage.branding.accentColor')}</FormLabel>
          <HStack>
            <Input
              type="color"
              value={settings.color_accent}
              onChange={(e) => updateField('color_accent', e.target.value)}
              w="50px"
              h="36px"
              p={0}
              border="none"
              cursor="pointer"
            />
            <Input
              size="sm"
              bg="gray.700"
              color="white"
              borderColor="gray.600"
              value={settings.color_accent}
              onChange={(e) => updateField('color_accent', e.target.value)}
              placeholder="#F4A261"
              maxW="120px"
            />
          </HStack>
        </FormControl>
      </HStack>

      <Divider borderColor="gray.600" />

      {/* Typography & Spacing — Tasks 52–56 */}
      <TypographySettings
        fontHeading={settings.font_heading}
        fontBody={settings.font_body}
        baseSpacing={settings.base_spacing}
        borderRadiusGlobal={settings.border_radius_global}
        shadowStyle={settings.shadow_style}
        onFontHeadingChange={(v) => updateField('font_heading', v)}
        onFontBodyChange={(v) => updateField('font_body', v)}
        onSpacingChange={(v) => updateField('base_spacing', v)}
        onRadiusChange={(v) => updateField('border_radius_global', v)}
        onShadowChange={(v) => updateField('shadow_style', v)}
      />

      {/* Contact Info */}
      <SectionHeading title={t('landingPage.branding.contactInfo')} />
      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        <BrandingField
          label={t('landingPage.branding.address')}
          value={settings.address}
          onChange={(v) => updateField('address', v)}
        />
        <BrandingField
          label={t('landingPage.branding.postalCity')}
          value={settings.postal_city}
          onChange={(v) => updateField('postal_city', v)}
          placeholder="1015 AA Amsterdam"
        />
        <BrandingField
          label={t('landingPage.branding.country')}
          value={settings.country}
          onChange={(v) => updateField('country', v)}
        />
        <BrandingField
          label={t('landingPage.branding.phone')}
          value={settings.phone}
          onChange={(v) => updateField('phone', v)}
          placeholder="+31 20 123 4567"
        />
        <BrandingField
          label={t('landingPage.branding.email')}
          value={settings.email}
          onChange={(v) => updateField('email', v)}
          placeholder="info@example.nl"
        />
        <BrandingField
          label={t('landingPage.branding.coc')}
          value={settings.coc}
          onChange={(v) => updateField('coc', v)}
          placeholder="KVK nummer"
        />
        <BrandingField
          label={t('landingPage.branding.vat')}
          value={settings.vat}
          onChange={(v) => updateField('vat', v)}
          placeholder="NL123456789B01"
        />
      </SimpleGrid>

      <Divider borderColor="gray.600" />

      {/* Social Media Links — Task 3.16 */}
      <SectionHeading title={t('landingPage.branding.socialLinks')} />
      <Text color="gray.400" fontSize="xs" mb={2}>
        {t('landingPage.branding.socialLinksHelp')}
      </Text>
      <VStack spacing={3} align="stretch">
        {SOCIAL_PLATFORMS.map((platform) => (
          <SocialLinkInput
            key={platform.key}
            platform={platform}
            value={settings.social_links[platform.key] || ''}
            error={socialErrors[platform.key]}
            onChange={(v) => updateSocialLink(platform.key, v)}
          />
        ))}
      </VStack>

      <Divider borderColor="gray.600" />

      {/* Share Buttons Toggle — Task 3.19 */}
      <SectionHeading title={t('landingPage.branding.shareButtons')} />
      <FormControl display="flex" alignItems="center">
        <Switch
          id="show-share-buttons"
          isChecked={settings.show_share_buttons}
          onChange={(e) => updateField('show_share_buttons', e.target.checked)}
          colorScheme="orange"
          size="md"
          mr={3}
        />
        <FormLabel htmlFor="show-share-buttons" color="gray.300" fontSize="sm" mb={0}>
          {t('landingPage.branding.showShareButtons')}
        </FormLabel>
      </FormControl>
      <Text color="gray.400" fontSize="xs">
        {t('landingPage.branding.showShareButtonsHelp')}
      </Text>

      <Divider borderColor="gray.600" />
    </VStack>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

function SectionHeading({ title }: { title: string }) {
  return (
    <Text color="white" fontWeight="bold" fontSize="sm" mt={2}>
      {title}
    </Text>
  );
}

interface BrandingFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

function BrandingField({ label, value, onChange, placeholder }: BrandingFieldProps) {
  return (
    <FormControl>
      <FormLabel color="gray.300" fontSize="xs" mb={1}>{label}</FormLabel>
      <Input
        size="sm"
        bg="gray.700"
        color="white"
        borderColor="gray.600"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        _placeholder={{ color: 'gray.500' }}
      />
    </FormControl>
  );
}

interface SocialLinkInputProps {
  platform: SocialPlatform;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}

function SocialLinkInput({ platform, value, error, onChange }: SocialLinkInputProps) {
  return (
    <FormControl isInvalid={!!error}>
      <InputGroup size="sm">
        <InputLeftElement pointerEvents="none">
          <Icon as={platform.icon} color={value ? 'orange.300' : 'gray.500'} />
        </InputLeftElement>
        <Input
          bg="gray.700"
          color="white"
          borderColor={error ? 'red.400' : 'gray.600'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={platform.placeholder}
          _placeholder={{ color: 'gray.500' }}
          pl="2.5rem"
        />
      </InputGroup>
      {error && (
        <FormErrorMessage fontSize="xs">{error}</FormErrorMessage>
      )}
    </FormControl>
  );
}
