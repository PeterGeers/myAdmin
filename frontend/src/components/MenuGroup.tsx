import React, { useState, useCallback } from 'react';
import { Box, Button, Collapse, VStack } from '@chakra-ui/react';

interface MenuGroupProps {
  icon: string;
  label: string;
  colorScheme?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

/**
 * Collapsible menu group for navigation sidebar.
 * - Toggle button matches direct nav button styling (size="lg", solid)
 * - Children rendered at smaller size with indentation
 * - Auto-collapses when a child button is clicked
 */
export function MenuGroup({
  icon,
  label,
  colorScheme = 'gray',
  defaultOpen = false,
  children,
}: MenuGroupProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  const handleChildClick = useCallback(() => {
    setIsOpen(false);
  }, []);

  return (
    <Box w="100%">
      <Button
        size="lg"
        w="full"
        variant="solid"
        colorScheme={colorScheme}
        justifyContent="flex-start"
        onClick={() => setIsOpen(!isOpen)}
      >
        {icon} {label} {isOpen ? '▾' : '▸'}
      </Button>
      <Collapse in={isOpen} animateOpacity>
        <VStack pl={6} spacing={1} align="stretch" mt={1} onClick={handleChildClick}>
          {children}
        </VStack>
      </Collapse>
    </Box>
  );
}
