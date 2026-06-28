/**
 * STRBookingTable Component
 *
 * Reusable table for displaying STR bookings (realised, planned, already loaded).
 * Used in tabs within the STRProcessor results section.
 */

import React from 'react';
import {
  Table, Thead, Tbody, Tr, Th, Td, TableContainer, Input,
} from '@chakra-ui/react';
import { authenticatedPost } from '../services/apiService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface STRBooking {
  sourceFile: string;
  channel: string;
  listing: string;
  checkinDate: string;
  checkoutDate?: string;
  nights: number;
  guests?: number;
  amountGross: number;
  amountChannelFee?: number;
  amountNett?: number;
  amountVat?: number;
  amountTouristTax?: number;
  guestName: string;
  reservationCode: string;
  status: string;
}

interface STRBookingTableProps {
  bookings: STRBooking[];
  /** If true, VRBO gross column is editable */
  editable?: boolean;
  /** Callback when bookings are updated (for editable VRBO rows) */
  onBookingsChange?: (bookings: STRBooking[]) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const STRBookingTable: React.FC<STRBookingTableProps> = ({
  bookings,
  editable = false,
  onBookingsChange,
  t,
}) => {
  if (bookings.length === 0) return null;

  const handleGrossBlur = async (index: number, newValue: string) => {
    if (!onBookingsChange) return;
    const newGross = parseFloat(newValue) || 0;
    const channelFee = newGross * 0.25;
    try {
      const resp = await authenticatedPost('/api/str/calculate-taxes', {
        amountGross: newGross,
        checkinDate: bookings[index].checkinDate,
        channelFee: channelFee,
      });
      const tax = await resp.json();
      if (tax.success) {
        const updated = [...bookings];
        updated[index] = {
          ...updated[index],
          amountGross: Math.round(newGross * 100) / 100,
          amountChannelFee: Math.round(channelFee * 100) / 100,
          amountVat: tax.amountVat,
          amountTouristTax: tax.amountTouristTax,
          amountNett: tax.amountNett,
        };
        onBookingsChange(updated);
      }
    } catch { /* keep current values */ }
  };

  return (
    <TableContainer>
      <Table size="sm" variant="simple">
        <Thead>
          <Tr>
            <Th color="gray.300">{t('processor.table.channel')}</Th>
            <Th color="gray.300">{t('processor.table.guest')}</Th>
            <Th color="gray.300">{t('processor.table.listing')}</Th>
            <Th color="gray.300">{t('processor.table.checkIn')}</Th>
            <Th color="gray.300">{t('processor.table.checkOut')}</Th>
            <Th color="gray.300">{t('processor.table.nights')}</Th>
            <Th color="gray.300">{t('processor.table.guests')}</Th>
            <Th color="gray.300">{t('processor.table.gross')}</Th>
            <Th color="gray.300">{t('processor.table.fee')}</Th>
            <Th color="gray.300">{t('processor.table.net')}</Th>
            <Th color="gray.300">{t('processor.table.status')}</Th>
            <Th color="gray.300">{t('processor.table.code')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {bookings.map((booking, index) => (
            <Tr key={index}>
              <Td color="white">{booking.channel}</Td>
              <Td color="white">{booking.guestName}</Td>
              <Td color="white">{booking.listing}</Td>
              <Td color="white">{booking.checkinDate}</Td>
              <Td color="white">{booking.checkoutDate}</Td>
              <Td color="white">{booking.nights}</Td>
              <Td color="white">{booking.guests || 0}</Td>
              <Td color="white">
                {editable && booking.channel === 'vrbo' ? (
                  <Input
                    size="xs" type="number" step="0.01" w="90px"
                    defaultValue={booking.amountGross?.toFixed(2) || '0.00'}
                    bg="gray.600" color="white" borderColor="gray.500"
                    onBlur={(e) => handleGrossBlur(index, e.target.value)}
                  />
                ) : (
                  <>€{booking.amountGross ? booking.amountGross.toFixed(2) : '0.00'}</>
                )}
              </Td>
              <Td color="white">€{booking.amountChannelFee ? booking.amountChannelFee.toFixed(2) : '0.00'}</Td>
              <Td color="white">€{booking.amountNett ? booking.amountNett.toFixed(2) : '0.00'}</Td>
              <Td color="white">{booking.status}</Td>
              <Td color="white">{booking.reservationCode}</Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </TableContainer>
  );
};
