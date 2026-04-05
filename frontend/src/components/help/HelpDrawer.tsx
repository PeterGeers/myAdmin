import React, { useState } from 'react';
import {
  Drawer, DrawerBody, DrawerCloseButton, DrawerContent,
  DrawerHeader, DrawerOverlay, Link, Spinner, Text, VStack, Box
} from '@chakra-ui/react';
import { ExternalLinkIcon } from '@chakra-ui/icons';

interface HelpDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  helpUrl: string;
}

/**
 * Slide-out drawer that embeds the MkDocs documentation site in an iframe.
 * Shows the fully styled MkDocs page with search, navigation, and print support.
 */
const HelpDrawer: React.FC<HelpDrawerProps> = ({ isOpen, onClose, helpUrl }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const handleLoad = () => {
    setLoading(false);
    setError(false);
    // Hide the MkDocs language switcher inside the iframe
    // (language is controlled by the app's LanguageSelector instead)
    try {
      const iframe = document.querySelector<HTMLIFrameElement>('iframe[title="Documentation"]');
      const iframeDoc = iframe?.contentDocument || iframe?.contentWindow?.document;
      if (iframeDoc) {
        const style = iframeDoc.createElement('style');
        style.textContent = '.md-select { display: none !important; }';
        iframeDoc.head.appendChild(style);
      }
    } catch {
      // Cross-origin iframe — can't inject CSS, ignore silently
    }
  };

  const handleError = () => {
    setLoading(false);
    setError(true);
  };

  return (
    <Drawer isOpen={isOpen} onClose={onClose} placement="right" size="lg">
      <DrawerOverlay />
      <DrawerContent bg="white">
        <DrawerCloseButton zIndex={10} />
        <DrawerHeader borderBottomWidth="1px" bg="gray.800" py={2}>
          <Link href={helpUrl} isExternal color="orange.400" fontSize="sm">
            Open in nieuw venster <ExternalLinkIcon mx="2px" />
          </Link>
        </DrawerHeader>
        <DrawerBody p={0}>
          {loading && (
            <VStack py={10}>
              <Spinner color="orange.400" size="lg" />
              <Text color="gray.500">Documentatie laden...</Text>
            </VStack>
          )}
          {error && (
            <VStack py={10}>
              <Text color="red.500">Kon documentatie niet laden.</Text>
              <Link href={helpUrl} isExternal color="orange.400">
                Open in nieuw venster <ExternalLinkIcon mx="2px" />
              </Link>
            </VStack>
          )}
          <Box
            as="iframe"
            src={isOpen ? helpUrl : undefined}
            title="Documentation"
            width="100%"
            height="100%"
            border="none"
            display={loading || error ? 'none' : 'block'}
            onLoad={handleLoad}
            onError={handleError}
          />
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default HelpDrawer;
