import React, { useState } from 'react';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Heading,
  Input,
  Text,
  Textarea,
  VStack,
  Alert,
  AlertIcon,
  Container,
} from '@chakra-ui/react';

// reCAPTCHA v3 global type declaration (Task 4.9)
declare global {
  interface Window {
    grecaptcha?: {
      execute: (siteKey: string, options: { action: string }) => Promise<string>;
      ready: (callback: () => void) => void;
    };
  }
}

export interface ContactBlockProps {
  properties: {
    title?: string;
    subtitle?: string;
  };
  layout: string;
  tenantSlug: string;
  settings?: {
    captcha_enabled?: boolean;
    captcha_site_key?: string;
  };
}

type FormState = 'idle' | 'submitting' | 'success' | 'error';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/**
 * Contact form block for public landing pages.
 *
 * Renders a name/email/message form that submits to the public
 * contact endpoint. Includes a honeypot field for bot detection
 * (hidden via CSS positioning, not display:none).
 */
export const ContactBlock: React.FC<ContactBlockProps> = ({
  properties,
  layout,
  tenantSlug,
  settings,
}) => {
  const { title, subtitle } = properties || {};
  const captchaEnabled = settings?.captcha_enabled && settings?.captcha_site_key;

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [honeypot, setHoneypot] = useState('');
  const [formState, setFormState] = useState<FormState>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  // Load reCAPTCHA v3 script when CAPTCHA is enabled (Task 4.9)
  React.useEffect(() => {
    if (!captchaEnabled || !settings?.captcha_site_key) return;
    // Skip if already loaded
    if (document.querySelector('script[src*="recaptcha"]')) return;

    const script = document.createElement('script');
    script.src = `https://www.google.com/recaptcha/api.js?render=${settings.captcha_site_key}`;
    script.async = true;
    document.head.appendChild(script);
  }, [captchaEnabled, settings?.captcha_site_key]);

  const isValidEmail = (value: string): boolean => {
    return /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/.test(value);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Client-side validation
    if (!name.trim() || !email.trim() || !message.trim()) {
      setErrorMessage('Please fill in all fields.');
      setFormState('error');
      return;
    }

    if (!isValidEmail(email.trim())) {
      setErrorMessage('Please enter a valid email address.');
      setFormState('error');
      return;
    }

    setFormState('submitting');
    setErrorMessage('');

    try {
      // Get reCAPTCHA token if CAPTCHA is enabled (Task 4.9)
      let captchaToken: string | undefined;
      if (captchaEnabled && window.grecaptcha) {
        try {
          captchaToken = await window.grecaptcha.execute(settings!.captcha_site_key!, {
            action: 'contact_form',
          });
        } catch {
          // If reCAPTCHA fails, proceed without token (graceful degradation)
        }
      }

      const response = await fetch(
        `${API_BASE_URL}/api/public/landing/${tenantSlug}/contact`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name.trim(),
            email: email.trim(),
            message: message.trim(),
            honeypot,
            ...(captchaToken && { captcha_token: captchaToken }),
          }),
        }
      );

      const result = await response.json();

      if (response.ok && result.success) {
        setFormState('success');
        setName('');
        setEmail('');
        setMessage('');
      } else if (response.status === 429) {
        setErrorMessage('Too many requests. Please try again later.');
        setFormState('error');
      } else {
        setErrorMessage(result.error || 'Something went wrong. Please try again.');
        setFormState('error');
      }
    } catch {
      setErrorMessage('Failed to send message. Please check your connection and try again.');
      setFormState('error');
    }
  };

  const isCentered = layout === 'centered' || !layout;

  return (
    <Box
      py={{ base: 12, md: 20 }}
      px={{ base: 6, md: 12 }}
      bg="gray.50"
    >
      <Container maxW="600px" mx="auto" textAlign={isCentered ? 'center' : 'left'}>
        {title && (
          <Heading as="h2" size="xl" mb={3}>
            {title}
          </Heading>
        )}
        {subtitle && (
          <Text fontSize="lg" color="gray.600" mb={8}>
            {subtitle}
          </Text>
        )}

        {formState === 'success' ? (
          <Alert status="success" borderRadius="md">
            <AlertIcon />
            Your message has been sent. We&apos;ll get back to you soon.
          </Alert>
        ) : (
          <Box as="form" onSubmit={handleSubmit} textAlign="left">
            <VStack spacing={4} align="stretch">
              {/* Honeypot — hidden from real users via CSS positioning */}
              <Box
                position="absolute"
                left="-9999px"
                top="-9999px"
                aria-hidden="true"
                tabIndex={-1}
              >
                <Input
                  type="text"
                  name="website"
                  autoComplete="off"
                  value={honeypot}
                  onChange={(e) => setHoneypot(e.target.value)}
                  tabIndex={-1}
                />
              </Box>

              <FormControl isRequired>
                <FormLabel color="gray.700">Name</FormLabel>
                <Input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  bg="white"
                  maxLength={200}
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel color="gray.700">Email</FormLabel>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  bg="white"
                  maxLength={200}
                />
              </FormControl>

              <FormControl isRequired>
                <FormLabel color="gray.700">Message</FormLabel>
                <Textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="How can we help you?"
                  bg="white"
                  rows={5}
                />
              </FormControl>

              {formState === 'error' && errorMessage && (
                <Alert status="error" borderRadius="md">
                  <AlertIcon />
                  {errorMessage}
                </Alert>
              )}

              <Button
                type="submit"
                size="lg"
                bg="var(--brand-primary, #2D6A4F)"
                color="white"
                _hover={{ opacity: 0.9 }}
                isLoading={formState === 'submitting'}
                loadingText="Sending..."
                isDisabled={formState === 'submitting'}
                w="full"
              >
                Send Message
              </Button>
            </VStack>
          </Box>
        )}
      </Container>
    </Box>
  );
};
