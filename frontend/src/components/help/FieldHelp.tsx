import React from 'react';
import { IconButton, Popover, PopoverArrow, PopoverBody, PopoverContent, PopoverTrigger, Link, Text, VStack } from '@chakra-ui/react';
import { InfoOutlineIcon } from '@chakra-ui/icons';
import { ExternalLinkIcon } from '@chakra-ui/icons';
import { getHelpUrl } from './helpLinks';

interface FieldHelpProps {
  /** Short tooltip text explaining the action */
  tooltip: string;
  /** Docs section path (e.g., "banking/pattern-matching") appended to base URL */
  docsSection?: string;
}

/**
 * Info icon with popover tooltip and optional "Learn more" link.
 * Used next to complex fields and action buttons.
 */
const FieldHelp: React.FC<FieldHelpProps> = ({ tooltip, docsSection }) => {
  const docsUrl = docsSection ? getHelpUrl('menu').replace(/\/$/, '') + '/' + docsSection + '/' : undefined;

  return (
    <Popover trigger="hover" placement="top">
      <PopoverTrigger>
        <IconButton
          aria-label="Field help"
          icon={<InfoOutlineIcon />}
          size="xs"
          variant="ghost"
          color="gray.400"
          _hover={{ color: 'orange.300' }}
          minW="auto"
        />
      </PopoverTrigger>
      <PopoverContent bg="gray.700" borderColor="gray.600" maxW="280px">
        <PopoverArrow bg="gray.700" />
        <PopoverBody>
          <VStack align="start" spacing={1}>
            <Text fontSize="sm" color="white">{tooltip}</Text>
            {docsUrl && (
              <Link href={docsUrl} isExternal color="orange.300" fontSize="xs">
                Meer informatie <ExternalLinkIcon mx="2px" />
              </Link>
            )}
          </VStack>
        </PopoverBody>
      </PopoverContent>
    </Popover>
  );
};

export default FieldHelp;
