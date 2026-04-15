/**
 * Invoice status badge with color mapping.
 * Reference: .kiro/specs/zzp-module/design.md §6.2
 */

import React from 'react';
import { Badge } from '@chakra-ui/react';
import { InvoiceStatus } from '../../types/zzp';

const STATUS_COLORS: Record<InvoiceStatus, string> = {
  draft: 'gray',
  sent: 'blue',
  paid: 'green',
  overdue: 'red',
  cancelled: 'orange',
  credited: 'purple',
};

interface InvoiceStatusBadgeProps {
  status: InvoiceStatus;
}

export const InvoiceStatusBadge: React.FC<InvoiceStatusBadgeProps> = ({ status }) => (
  <Badge colorScheme={STATUS_COLORS[status] || 'gray'} variant="subtle">
    {status}
  </Badge>
);
