/**
 * UserRoleEditor Component
 *
 * Reusable role checkbox list for create/edit user modals.
 */

import React from 'react';
import {
  FormControl, FormLabel, Stack, Checkbox, VStack, Text,
} from '@chakra-ui/react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Role {
  name: string;
  description: string;
  precedence: number | null;
}

interface UserRoleEditorProps {
  roles: Role[];
  selectedRoles: string[];
  onRolesChange: (roles: string[]) => void;
  label: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const UserRoleEditor: React.FC<UserRoleEditorProps> = ({
  roles,
  selectedRoles,
  onRolesChange,
  label,
}) => {
  const handleToggle = (roleName: string, checked: boolean) => {
    if (checked) {
      onRolesChange([...selectedRoles, roleName]);
    } else {
      onRolesChange(selectedRoles.filter(r => r !== roleName));
    }
  };

  return (
    <FormControl>
      <FormLabel color="gray.300">{label}</FormLabel>
      <Stack spacing={2} bg="gray.700" p={3} borderRadius="md">
        {roles.map(role => (
          <Checkbox
            key={role.name}
            isChecked={selectedRoles.includes(role.name)}
            onChange={(e) => handleToggle(role.name, e.target.checked)}
            colorScheme="orange"
            color="white"
          >
            <VStack align="start" spacing={0}>
              <Text fontWeight="bold">{role.name}</Text>
              {role.description && (
                <Text fontSize="xs" color="gray.400">{role.description}</Text>
              )}
            </VStack>
          </Checkbox>
        ))}
      </Stack>
    </FormControl>
  );
};
