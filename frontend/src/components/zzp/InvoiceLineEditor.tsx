/**
 * Editable invoice line items table.
 * Supports product lookup, quantity, price, VAT code, calculated totals.
 * Reference: .kiro/specs/zzp-module/design.md §6.3
 */

import React from 'react';
import {
  Table, Thead, Tbody, Tr, Th, Td,
  Input, Select, IconButton, HStack, Text,
} from '@chakra-ui/react';
import { AddIcon, DeleteIcon } from '@chakra-ui/icons';
import { InvoiceLine, Product } from '../../types/zzp';

interface InvoiceLineEditorProps {
  lines: Partial<InvoiceLine>[];
  products: Product[];
  readOnly?: boolean;
  onChange: (lines: Partial<InvoiceLine>[]) => void;
}

const VAT_CODES = ['high', 'low', 'zero'];

export const InvoiceLineEditor: React.FC<InvoiceLineEditorProps> = ({
  lines, products, readOnly = false, onChange,
}) => {
  const updateLine = (idx: number, field: string, value: any) => {
    const updated = [...lines];
    updated[idx] = { ...updated[idx], [field]: value };

    // Auto-fill from product
    if (field === 'product_id' && value) {
      const product = products.find(p => p.id === Number(value));
      if (product) {
        updated[idx].description = product.name;
        updated[idx].unit_price = product.unit_price;
        updated[idx].vat_code = product.vat_code;
      }
    }

    // Recalculate line total
    const qty = Number(updated[idx].quantity) || 0;
    const price = Number(updated[idx].unit_price) || 0;
    updated[idx].line_total = Math.round(qty * price * 100) / 100;

    onChange(updated);
  };

  const addLine = () => {
    onChange([...lines, { description: '', quantity: 1, unit_price: 0, vat_code: 'high', line_total: 0 }]);
  };

  const removeLine = (idx: number) => {
    onChange(lines.filter((_, i) => i !== idx));
  };

  return (
    <>
      <Table size="sm" variant="simple">
        <Thead>
          <Tr>
            <Th>Product</Th>
            <Th>Omschrijving</Th>
            <Th isNumeric>Aantal</Th>
            <Th isNumeric>Prijs</Th>
            <Th>BTW</Th>
            <Th isNumeric>Totaal</Th>
            {!readOnly && <Th />}
          </Tr>
        </Thead>
        <Tbody>
          {lines.map((line, idx) => (
            <Tr key={idx}>
              <Td>
                {readOnly ? (
                  <Text fontSize="sm">{products.find(p => p.id === line.product_id)?.name || '-'}</Text>
                ) : (
                  <Select size="sm" value={line.product_id || ''} placeholder="-"
                    onChange={e => updateLine(idx, 'product_id', e.target.value)}>
                    {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </Select>
                )}
              </Td>
              <Td>
                {readOnly ? <Text fontSize="sm">{line.description}</Text> : (
                  <Input size="sm" value={line.description || ''}
                    onChange={e => updateLine(idx, 'description', e.target.value)} />
                )}
              </Td>
              <Td isNumeric>
                {readOnly ? <Text fontSize="sm">{line.quantity}</Text> : (
                  <Input size="sm" type="number" step="0.01" w="80px" value={line.quantity || ''}
                    onChange={e => updateLine(idx, 'quantity', parseFloat(e.target.value))} />
                )}
              </Td>
              <Td isNumeric>
                {readOnly ? <Text fontSize="sm">&euro; {Number(line.unit_price || 0).toFixed(2)}</Text> : (
                  <Input size="sm" type="number" step="0.01" w="100px" value={line.unit_price || ''}
                    onChange={e => updateLine(idx, 'unit_price', parseFloat(e.target.value))} />
                )}
              </Td>
              <Td>
                {readOnly ? <Text fontSize="sm">{line.vat_code}</Text> : (
                  <Select size="sm" value={line.vat_code || 'high'} w="90px"
                    onChange={e => updateLine(idx, 'vat_code', e.target.value)}>
                    {VAT_CODES.map(c => <option key={c} value={c}>{c}</option>)}
                  </Select>
                )}
              </Td>
              <Td isNumeric>
                <Text fontSize="sm">&euro; {Number(line.line_total || 0).toFixed(2)}</Text>
              </Td>
              {!readOnly && (
                <Td>
                  <IconButton aria-label="Remove line" icon={<DeleteIcon />} size="xs"
                    variant="ghost" colorScheme="red" onClick={() => removeLine(idx)} />
                </Td>
              )}
            </Tr>
          ))}
        </Tbody>
      </Table>
      {!readOnly && (
        <HStack mt={2}>
          <IconButton aria-label="Add line" icon={<AddIcon />} size="sm"
            variant="outline" colorScheme="orange" color="orange.300" onClick={addLine} />
        </HStack>
      )}
    </>
  );
};
