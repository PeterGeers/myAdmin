import {
  Box,
  Container,
  Flex,
  HStack,
  Icon,
  Link,
  Stack,
  Text,
} from '@chakra-ui/react';
import {
  FaInstagram,
  FaFacebook,
  FaAirbnb,
  FaLinkedin,
  FaYoutube,
  FaTiktok,
  FaXTwitter,
  FaHotel,
} from 'react-icons/fa6';
import type { IconType } from 'react-icons';

export interface PublicFooterProps {
  footer: {
    company_name: string;
    address: string;
    postal_city: string;
    country: string;
    phone: string;
    email: string;
    coc: string;
    vat: string;
    social_links: Record<string, string>;
  };
}

const SOCIAL_ICON_MAP: Record<string, { icon: IconType; label: string }> = {
  instagram: { icon: FaInstagram, label: 'Instagram' },
  facebook: { icon: FaFacebook, label: 'Facebook' },
  airbnb: { icon: FaAirbnb, label: 'Airbnb' },
  booking_com: { icon: FaHotel, label: 'Booking.com' },
  linkedin: { icon: FaLinkedin, label: 'LinkedIn' },
  youtube: { icon: FaYoutube, label: 'YouTube' },
  tiktok: { icon: FaTiktok, label: 'TikTok' },
  twitter_x: { icon: FaXTwitter, label: 'X (Twitter)' },
};

export function PublicFooter({ footer }: PublicFooterProps) {
  const activeSocialLinks = Object.entries(footer.social_links).filter(
    ([, url]) => url && url.trim().length > 0
  );

  return (
    <Box as="footer" bg="gray.800" color="white" py={{ base: 8, md: 10 }}>
      <Container maxW="1200px" px={{ base: 6, md: 8 }}>
        <Stack
          direction={{ base: 'column', md: 'row' }}
          spacing={8}
          justify="space-between"
          align={{ base: 'flex-start', md: 'flex-start' }}
        >
          {/* Company info */}
          <Stack spacing={1}>
            <Text fontWeight="bold" fontSize="lg">
              {footer.company_name}
            </Text>
            <Text fontSize="sm" color="gray.300">
              {footer.address}
            </Text>
            <Text fontSize="sm" color="gray.300">
              {footer.postal_city}
              {footer.country ? `, ${footer.country}` : ''}
            </Text>
          </Stack>

          {/* Contact info */}
          <Stack spacing={1}>
            {footer.phone && (
              <Link
                href={`tel:${footer.phone}`}
                fontSize="sm"
                color="gray.300"
                _hover={{ color: 'white' }}
              >
                Tel: {footer.phone}
              </Link>
            )}
            {footer.email && (
              <Link
                href={`mailto:${footer.email}`}
                fontSize="sm"
                color="gray.300"
                _hover={{ color: 'white' }}
              >
                {footer.email}
              </Link>
            )}
          </Stack>

          {/* Business info */}
          <Stack spacing={1}>
            {footer.coc && (
              <Text fontSize="sm" color="gray.300">
                KVK: {footer.coc}
              </Text>
            )}
            {footer.vat && (
              <Text fontSize="sm" color="gray.300">
                BTW: {footer.vat}
              </Text>
            )}
          </Stack>

          {/* Social icons */}
          {activeSocialLinks.length > 0 && (
            <Stack spacing={2}>
              <Text fontWeight="bold" fontSize="sm" color="gray.400">
                Volg ons
              </Text>
              <HStack spacing={3}>
                {activeSocialLinks.map(([platform, url]) => {
                  const socialInfo = SOCIAL_ICON_MAP[platform];
                  if (!socialInfo) return null;
                  return (
                    <Link
                      key={platform}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`Visit us on ${socialInfo.label}`}
                      color="gray.300"
                      _hover={{ color: 'white', transform: 'scale(1.15)' }}
                      transition="all 0.2s"
                    >
                      <Icon as={socialInfo.icon} boxSize={5} />
                    </Link>
                  );
                })}
              </HStack>
            </Stack>
          )}
        </Stack>

        {/* Copyright */}
        <Flex
          mt={8}
          pt={4}
          borderTop="1px"
          borderColor="gray.600"
          justify="center"
        >
          <Text fontSize="xs" color="gray.500">
            © {new Date().getFullYear()} {footer.company_name}. Alle rechten
            voorbehouden.
          </Text>
        </Flex>
      </Container>
    </Box>
  );
}
