import React from 'react';
import { Box, Container, Heading } from '@chakra-ui/react';
import { PublicApplicationPage } from '../../../components/public/application/PublicApplicationPage';
import { ApplicationFormPage } from '../../../components/public/application/ApplicationFormPage';

export interface ApplicationFormBlockProps {
  properties: {
    /** Optional block heading shown above the form (bilingual-agnostic plain string). */
    title?: string;
    /** Optional initial locale for the form (nl/en); the form itself also offers a selector. */
    locale?: string;
  };
  layout: string;
  /** The tenant slug — drives the public field-config fetch (same-origin, no iframe). */
  tenantSlug: string;
}

/**
 * Application-form landing-page block (spec Members/11 task 3.2a, E4a / R5.2a).
 *
 * Renders the tenant's PUBLIC member-application form as a NATIVE, same-origin section of the
 * landing page — NOT an iframe embed. It reuses the exact public composition the standalone
 * `/apply` route uses: `PublicApplicationPage` fetches the public field-config by slug (and owns
 * the neutral loading / 404 / "not accepting applications" states), and `ApplicationFormPage`
 * renders the config-driven form + submit/consent/locale wiring through the shared
 * `ApplicationFormRenderer`. Because it is same-origin, it needs NO `frame-ancestors` / embed-origin
 * configuration — that machinery is only for FOREIGN-site iframe embedding (E4b).
 *
 * The `contained` layout wraps the form in a narrower column; `full-width` lets it span the
 * section. Both are same-origin; layout only affects width.
 */
export const ApplicationFormBlock: React.FC<ApplicationFormBlockProps> = ({
  properties,
  layout,
  tenantSlug,
}) => {
  const { title, locale } = properties || {};
  if (!tenantSlug) return null;

  const maxW = layout === 'full-width' ? '1200px' : '720px';

  return (
    <Container maxW={maxW} px={{ base: 6, md: 12 }} py={{ base: 12, md: 16 }}>
      {title && (
        <Heading as="h2" size="xl" textAlign="center" mb={8}>
          {title}
        </Heading>
      )}
      <Box data-testid="application-form-block">
        <PublicApplicationPage
          tenantSlug={tenantSlug}
          renderForm={(config) => (
            <ApplicationFormPage
              tenantSlug={tenantSlug}
              config={config}
              initialLocale={locale}
            />
          )}
        />
      </Box>
    </Container>
  );
};

export default ApplicationFormBlock;
