import React from 'react';
import { ChakraProvider, extendTheme } from '@chakra-ui/react';

interface PublicThemeProviderProps {
  children: React.ReactNode;
  branding: {
    color_primary: string;
    color_accent: string;
  };
}

export function PublicThemeProvider({ children, branding }: PublicThemeProviderProps) {
  const theme = extendTheme({
    colors: {
      brand: {
        primary: branding.color_primary || '#2D5F8A',
        accent: branding.color_accent || '#F4A261',
      },
    },
    styles: {
      global: {
        body: {
          bg: 'white',
          color: 'gray.800',
        },
      },
    },
  });

  return <ChakraProvider theme={theme}>{children}</ChakraProvider>;
}
