/**
 * Surface-to-component map — total over ADMIN_SURFACE_REGISTRY ids.
 *
 * Every id the backend can emit MUST be registered here so a missing component
 * never silently drops a surface (design §Correctness Properties 7). Ids are
 * kept in registry order so tabs and panels derive from one ordered array.
 *
 * MembersAdminPanel is a pure extraction of the former inline Members block
 * (Requirements 5.2, 9.x).
 */

import { Box, Text } from '@chakra-ui/react';
import { AdminSurface } from '../../hooks/useTenantAdminSurfaces';
import UserManagement from './UserManagement';
import FinancialTab from './FinancialTab';
import MembersAdminPanel from './MembersAdminPanel';
import StorageTab from './StorageTab';
import MediaAssetAdminPage from '../../pages/MediaAssetAdminPage';
import TemplateManagement from './TemplateManagement/TemplateManagement';
import TenantInfoTab from './TenantInfoTab';
import SenderSettingsTab from './SenderSettingsTab';
import FunctionsTab from './FunctionsTab';
import { LandingPageEditor } from './LandingPage';
import AdvancedTab from './AdvancedTab';
import { PivotBuilderWithPreview } from '../pivot/PivotBuilderWithPreview';

interface SurfaceProps {
  tenant?: string;
  tenantModules?: string[];
}

interface SurfaceComponentProps {
  surface: AdminSurface;
  tenant?: string;
  tenantModules?: string[];
}

export const adminSurfaceComponents: Record<string, React.FC<SurfaceProps>> = {
  users: UserManagement,
  functions: FunctionsTab,
  financial: FinancialTab,
  members: MembersAdminPanel,
  storage: StorageTab,
  media: MediaAssetAdminPage,
  templates: TemplateManagement,
  'tenant-info': TenantInfoTab,
  sender: SenderSettingsTab,
  pivot: PivotBuilderWithPreview,
  landing: LandingPageEditor,
  advanced: AdvancedTab,
};

export function SurfaceComponent({ surface, tenant, tenantModules }: SurfaceComponentProps) {
  const Component = adminSurfaceComponents[surface.id];
  if (!Component) {
    return (
      <Box p={4}>
        <Text color="red.400">Unknown admin surface: {surface.id}</Text>
      </Box>
    );
  }
  return <Component tenant={tenant} tenantModules={tenantModules} />;
}
