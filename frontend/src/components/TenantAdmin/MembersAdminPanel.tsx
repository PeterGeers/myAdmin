/**
 * Members-owned admin panel.
 *
 * Pure extraction of the Members inline dashboard block: the three typed editor
 * sub-tabs and the co-located sender-identities surface are unchanged. This file
 * gives the registry component map a component to address by surface id.
 */

import { Box, Tabs, TabList, TabPanels, Tab, TabPanel, VStack } from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import MemberSenderIdentitiesTab from './MemberSenderIdentitiesTab';
import {
  MembersConfigEditor,
  MembersMailConfigEditor,
  ApplicationFormBuilder,
} from './MembersConfig';

interface MembersAdminPanelProps {
  tenant: string;
}

export default function MembersAdminPanel({ tenant }: MembersAdminPanelProps) {
  const { i18n } = useTypedTranslation('admin');
  const membersLang: 'nl' | 'en' = i18n.language?.startsWith('nl') ? 'nl' : 'en';

  return (
    <Box>
      {/* The membership_type enum editor was removed (task 8.1): membership types
          are now a normal enum field authored inline. */}
      <Tabs colorScheme="orange" variant="soft-rounded" size="sm" isLazy>
        <TabList>
          <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
            {membersLang === 'nl' ? 'Veldconfiguratie' : 'Field configuration'}
          </Tab>
          <Tab
            color="gray.300"
            _selected={{ color: 'orange.400', bg: 'gray.800' }}
            data-testid="members-admin-mail-tab"
          >
            Mail
          </Tab>
          <Tab
            color="gray.300"
            _selected={{ color: 'orange.400', bg: 'gray.800' }}
            data-testid="members-admin-application-form-tab"
          >
            {membersLang === 'nl' ? 'Aanmeldformulier' : 'Application form'}
          </Tab>
        </TabList>
        <TabPanels>
          <TabPanel px={0}>
            <MembersConfigEditor tenant={tenant} />
          </TabPanel>
          <TabPanel px={0}>
            {/* Mail config authors the SAM-owned config#mail scalars. Sender identities
                keep their own Flask route and are not folded into that put. */}
            <VStack align="stretch" spacing={8}>
              <MembersMailConfigEditor tenant={tenant} />
              <MemberSenderIdentitiesTab tenant={tenant} />
            </VStack>
          </TabPanel>
          <TabPanel px={0}>
            <ApplicationFormBuilder tenant={tenant} />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}
