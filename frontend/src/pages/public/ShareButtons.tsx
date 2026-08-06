/**
 * ShareButtons — Floating share bar for public landing pages.
 *
 * Renders share buttons for Facebook, X/Twitter, WhatsApp, LinkedIn, and Email.
 * Uses native platform share URLs — no API keys, no third-party scripts, no cookies.
 *
 * Only renders when settings.show_share_buttons is true.
 *
 * Tasks: 3.19, 3.20, 3.21
 */

import React from 'react';
import { Box, IconButton, VStack, useBreakpointValue } from '@chakra-ui/react';
import {
  FaFacebook,
  FaXTwitter,
  FaWhatsapp,
  FaLinkedin,
  FaEnvelope,
} from 'react-icons/fa6';

// ============================================================================
// Types
// ============================================================================

export interface ShareButtonsProps {
  /** The URL of the page to share */
  pageUrl: string;
  /** The title/text to accompany the shared link */
  title: string;
}

// ============================================================================
// Share URL builders (Task 3.21 — native URLs, no API keys)
// ============================================================================

function buildShareUrls(pageUrl: string, title: string) {
  const encodedUrl = encodeURIComponent(pageUrl);
  const encodedTitle = encodeURIComponent(title);

  return {
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`,
    twitter: `https://twitter.com/intent/tweet?url=${encodedUrl}&text=${encodedTitle}`,
    whatsapp: `https://wa.me/?text=${encodedTitle}%20${encodedUrl}`,
    linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`,
    email: `mailto:?subject=${encodedTitle}&body=${encodedUrl}`,
  };
}

// ============================================================================
// Component
// ============================================================================

export function ShareButtons({ pageUrl, title }: ShareButtonsProps) {
  const urls = buildShareUrls(pageUrl, title);

  // On mobile: horizontal bar at bottom. On desktop: vertical bar on left side.
  const isMobile = useBreakpointValue({ base: true, md: false });

  const buttons = [
    { label: 'Share on Facebook', icon: <FaFacebook />, url: urls.facebook, color: '#1877F2' },
    { label: 'Share on X', icon: <FaXTwitter />, url: urls.twitter, color: '#000000' },
    { label: 'Share on WhatsApp', icon: <FaWhatsapp />, url: urls.whatsapp, color: '#25D366' },
    { label: 'Share on LinkedIn', icon: <FaLinkedin />, url: urls.linkedin, color: '#0A66C2' },
    { label: 'Share via Email', icon: <FaEnvelope />, url: urls.email, color: '#6B7280' },
  ];

  if (isMobile) {
    // Horizontal fixed bar at the bottom
    return (
      <Box
        position="fixed"
        bottom={0}
        left={0}
        right={0}
        display="flex"
        justifyContent="center"
        gap={2}
        py={2}
        px={4}
        bg="white"
        borderTop="1px solid"
        borderColor="gray.200"
        boxShadow="0 -2px 10px rgba(0,0,0,0.1)"
        zIndex={50}
      >
        {buttons.map((btn) => (
          <IconButton
            key={btn.label}
            as="a"
            href={btn.url}
            target={btn.url.startsWith('mailto:') ? undefined : '_blank'}
            rel="noopener noreferrer"
            aria-label={btn.label}
            icon={btn.icon}
            size="md"
            variant="ghost"
            color={btn.color}
            _hover={{ bg: 'gray.100', transform: 'scale(1.1)' }}
            transition="all 0.2s"
          />
        ))}
      </Box>
    );
  }

  // Desktop: Vertical floating bar on the left side
  return (
    <Box
      position="fixed"
      left={4}
      top="50%"
      transform="translateY(-50%)"
      zIndex={50}
    >
      <VStack
        spacing={1}
        bg="white"
        borderRadius="lg"
        boxShadow="md"
        border="1px solid"
        borderColor="gray.200"
        p={2}
      >
        {buttons.map((btn) => (
          <IconButton
            key={btn.label}
            as="a"
            href={btn.url}
            target={btn.url.startsWith('mailto:') ? undefined : '_blank'}
            rel="noopener noreferrer"
            aria-label={btn.label}
            icon={btn.icon}
            size="sm"
            variant="ghost"
            color={btn.color}
            _hover={{ bg: 'gray.100', transform: 'scale(1.1)' }}
            transition="all 0.2s"
          />
        ))}
      </VStack>
    </Box>
  );
}

export default ShareButtons;
