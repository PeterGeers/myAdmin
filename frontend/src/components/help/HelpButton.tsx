import React from 'react';
import { IconButton, useDisclosure, useBreakpointValue } from '@chakra-ui/react';
import { QuestionOutlineIcon } from '@chakra-ui/icons';
import { useTranslation } from 'react-i18next';
import HelpDrawer from './HelpDrawer';
import { getHelpUrl } from './helpLinks';

interface HelpButtonProps {
  /** currentPage value from App.tsx */
  page: string;
}

/**
 * Help button — opens drawer on desktop, new tab on mobile.
 * Re-renders when app language changes so the correct docs version loads.
 */
const HelpButton: React.FC<HelpButtonProps> = ({ page }) => {
  const { isOpen, onOpen, onClose } = useDisclosure();
  const { i18n } = useTranslation();
  const helpUrl = getHelpUrl(page);
  const isMobile = useBreakpointValue({ base: true, md: false });
  const key = `${page}-${i18n.language}`;

  const handleClick = () => {
    if (isMobile) {
      window.open(helpUrl, '_blank', 'noopener');
    } else {
      onOpen();
    }
  };

  return (
    <>
      <IconButton
        aria-label="Help"
        icon={<QuestionOutlineIcon />}
        size="sm"
        variant="ghost"
        color="gray.300"
        _hover={{ color: 'orange.400' }}
        onClick={handleClick}
      />
      {!isMobile && (
        <HelpDrawer key={key} isOpen={isOpen} onClose={onClose} helpUrl={helpUrl} />
      )}
    </>
  );
};

export default HelpButton;
