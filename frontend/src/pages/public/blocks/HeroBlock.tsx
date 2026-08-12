import React from 'react';
import { Box, Flex, Heading, Text, Button, Image } from '@chakra-ui/react';

export interface HeroBlockProps {
  properties: {
    title: string;
    subtitle?: string;
    cta_text?: string;
    cta_url?: string;
    image_key?: string;
    video_url?: string;
  };
  layout: string;
  cloudFrontUrl: string;
}

/**
 * Hero section block renderer.
 *
 * Layout variants:
 * - image-right: Text left, image right (default)
 * - image-left: Image left, text right
 * - image-background: Full-width background image with overlaid text
 * - centered: Centered text with optional background image
 */
export const HeroBlock: React.FC<HeroBlockProps> = ({
  properties,
  layout,
  cloudFrontUrl,
}) => {
  const { title, subtitle, cta_text, cta_url, image_key, video_url } = properties || {};
  const imageUrl = image_key ? `${cloudFrontUrl}/${image_key}` : undefined;

  // Extract YouTube video ID
  const videoId = video_url?.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)/)?.[1] || '';

  // Determine if CTA url is external (opens new tab) or relative (same tab)
  const isExternalUrl = cta_url
    ? /^https?:\/\//.test(cta_url)
    : false;

  const ctaButton = cta_text ? (
    <Button
      as="a"
      href={cta_url || '#'}
      target={isExternalUrl ? '_blank' : undefined}
      rel={isExternalUrl ? 'noopener noreferrer' : undefined}
      size="lg"
      bg="var(--brand-accent, #F4A261)"
      color="white"
      _hover={{ opacity: 0.9 }}
      mt={4}
    >
      {cta_text}
    </Button>
  ) : null;

  const textContent = (
    <Box>
      <Heading as="h1" size="2xl" fontWeight="bold" mb={4}>
        {title}
      </Heading>
      {subtitle && (
        <Text fontSize="xl" opacity={0.9} mb={4}>
          {subtitle}
        </Text>
      )}
      {ctaButton}
    </Box>
  );

  // Layout: video-bg — YouTube video background with text overlay
  if (layout === 'video-bg') {
    return (
      <Box
        minH="60vh"
        position="relative"
        display="flex"
        alignItems="center"
        justifyContent="center"
        textAlign="center"
        overflow="hidden"
        bg="gray.900"
        px={{ base: 6, md: 12 }}
        py={{ base: 16, md: 24 }}
      >
        {/* Video background */}
        {videoId && (
          <Box
            as="iframe"
            position="absolute"
            top="50%"
            left="50%"
            minW="100%"
            minH="100%"
            transform="translate(-50%, -50%)"
            src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&mute=1&loop=1&playlist=${videoId}&controls=0`}
            frameBorder="0"
            allow="autoplay"
            zIndex={0}
          />
        )}
        {/* Dark overlay */}
        <Box position="absolute" inset={0} bg="blackAlpha.600" zIndex={1} />
        {/* Content */}
        <Box position="relative" zIndex={2} maxW="800px" color="white">
          {textContent}
        </Box>
      </Box>
    );
  }

  // Layout: image-bg — full-bleed background image with text overlay
  if (layout === 'image-bg') {
    return (
      <Box
        minH="60vh"
        position="relative"
        display="flex"
        alignItems="center"
        justifyContent="center"
        textAlign="center"
        bgImage={imageUrl ? `url(${imageUrl})` : undefined}
        bgSize="cover"
        bgPosition="center"
        color="white"
        px={{ base: 6, md: 12 }}
        py={{ base: 16, md: 24 }}
      >
        <Box position="absolute" inset={0} bg="blackAlpha.600" zIndex={0} />
        <Box position="relative" zIndex={1} maxW="800px">
          {textContent}
        </Box>
      </Box>
    );
  }

  // Layout: image-background — background image with text overlay
  if (layout === 'image-background') {
    return (
      <Box
        minH="60vh"
        position="relative"
        display="flex"
        alignItems="center"
        justifyContent="center"
        textAlign="center"
        bgImage={imageUrl ? `url(${imageUrl})` : undefined}
        bgSize="cover"
        bgPosition="center"
        color="white"
        px={{ base: 6, md: 12 }}
        py={{ base: 16, md: 24 }}
      >
        {/* Dark overlay for text readability */}
        <Box
          position="absolute"
          inset={0}
          bg="blackAlpha.600"
          zIndex={0}
        />
        <Box position="relative" zIndex={1} maxW="800px">
          {textContent}
        </Box>
      </Box>
    );
  }

  // Layout: centered — centered text, optional background
  if (layout === 'centered') {
    return (
      <Box
        minH="60vh"
        display="flex"
        alignItems="center"
        justifyContent="center"
        textAlign="center"
        bgImage={imageUrl ? `url(${imageUrl})` : undefined}
        bgSize="cover"
        bgPosition="center"
        position="relative"
        px={{ base: 6, md: 12 }}
        py={{ base: 16, md: 24 }}
      >
        {imageUrl && (
          <Box
            position="absolute"
            inset={0}
            bg="blackAlpha.400"
            zIndex={0}
          />
        )}
        <Box position="relative" zIndex={1} maxW="800px">
          {textContent}
        </Box>
      </Box>
    );
  }

  // Layout: split-diagonal — text left, diagonal clip-path image right
  if (layout === 'split-diagonal') {
    return (
      <Flex minH="60vh" position="relative" overflow="hidden">
        <Flex flex="1" direction="column" justify="center" px={{ base: 6, md: 12 }} py={16}>
          {textContent}
        </Flex>
        {imageUrl && (
          <Box flex="1" clipPath="polygon(15% 0, 100% 0, 100% 100%, 0% 100%)" bgImage={`url(${imageUrl})`} bgSize="cover" bgPosition="center" />
        )}
      </Flex>
    );
  }

  // Layout: image-left or image-right (default)
  const isImageLeft = layout === 'image-left';

  return (
    <Flex
      direction={{ base: 'column', md: isImageLeft ? 'row' : 'row-reverse' }}
      align="center"
    >
      {/* Image side */}
      {imageUrl && (
        <Box flex="1" p={{ base: 4, md: 6 }}>
          <Image
            src={imageUrl}
            alt={title || 'Hero image'}
            w="100%"
            h="auto"
            loading="lazy"
          />
        </Box>
      )}

      {/* Text side */}
      <Flex
        flex="1"
        direction="column"
        justify="center"
        px={{ base: 6, md: 12 }}
        py={{ base: 12, md: 16 }}
      >
        {textContent}
      </Flex>
    </Flex>
  );
};
