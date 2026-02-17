/**
 * Language Selector Component
 * 
 * Allows users to switch between Dutch (nl) and English (en) languages.
 * Saves preference to localStorage and backend API.
 */

import React, { useState, useEffect } from 'react';
import { Menu, MenuButton, MenuList, MenuItem, Button, useToast } from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import { ChevronDownIcon } from '@chakra-ui/icons';

interface Language {
  code: string;
  name: string;
  flag: string;
}

const languages: Language[] = [
  { code: 'nl', name: 'Nederlands', flag: '🇳🇱' },
  { code: 'en', name: 'English', flag: '🇬🇧' }
];

export const LanguageSelector: React.FC = () => {
  const { i18n } = useTranslation();
  const [currentLang, setCurrentLang] = useState(i18n.language);
  const toast = useToast();

  // Update state when i18n language changes
  useEffect(() => {
    setCurrentLang(i18n.language);
  }, [i18n.language]);

  const changeLanguage = async (langCode: string) => {
    try {
      // Change language in i18next (updates localStorage automatically)
      await i18n.changeLanguage(langCode);
      setCurrentLang(langCode);

      // Save to backend API (optional - will be implemented in Phase 3)
      try {
        const token = localStorage.getItem('idToken');
        if (token) {
          await fetch('/api/user/language', {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
              'X-Language': langCode
            },
            body: JSON.stringify({ language: langCode })
          });
        }
      } catch (apiError) {
        // API call failed, but language still changed locally
        console.warn('Failed to save language preference to backend:', apiError);
      }

      // Show success toast
      const langName = languages.find(l => l.code === langCode)?.name || langCode;
      toast({
        title: langCode === 'nl' ? 'Taal gewijzigd' : 'Language changed',
        description: langCode === 'nl' 
          ? `Taal ingesteld op ${langName}` 
          : `Language set to ${langName}`,
        status: 'success',
        duration: 2000,
        isClosable: true,
        position: 'top-right'
      });
    } catch (error) {
      console.error('Failed to change language:', error);
      toast({
        title: 'Error',
        description: 'Failed to change language',
        status: 'error',
        duration: 3000,
        isClosable: true,
        position: 'top-right'
      });
    }
  };

  const currentLanguage = languages.find(l => l.code === currentLang || currentLang.startsWith(l.code)) || languages[0];

  return (
    <Menu>
      <MenuButton
        as={Button}
        rightIcon={<ChevronDownIcon />}
        size="sm"
        variant="ghost"
        fontWeight="normal"
        color="white"
        _hover={{ bg: 'gray.700' }}
        _active={{ bg: 'gray.600' }}
      >
        <span style={{ marginRight: '8px' }}>{currentLanguage.flag}</span>
        {currentLanguage.code.toUpperCase()}
      </MenuButton>
      <MenuList minWidth="150px">
        {languages.map(lang => (
          <MenuItem
            key={lang.code}
            onClick={() => changeLanguage(lang.code)}
            bg={lang.code === currentLang || currentLang.startsWith(lang.code) ? 'blue.50' : 'transparent'}
            _hover={{ bg: 'gray.100' }}
          >
            <span style={{ marginRight: '12px', fontSize: '20px' }}>{lang.flag}</span>
            {lang.name}
          </MenuItem>
        ))}
      </MenuList>
    </Menu>
  );
};
