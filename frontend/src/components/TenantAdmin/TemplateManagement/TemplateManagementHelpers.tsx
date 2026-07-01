import React from 'react';
import { Box, VStack, Text } from '@chakra-ui/react';
import type { TemplateType } from '../../../services/templateApi';

/**
 * Helper function to read file as text
 */
export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      if (e.target?.result) {
        resolve(e.target.result as string);
      } else {
        reject(new Error('Failed to read file'));
      }
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsText(file);
  });
}

/**
 * Get required placeholders for template type
 */
export function getRequiredPlaceholders(templateType: TemplateType): string[] {
  const placeholders: Record<TemplateType, string[]> = {
    str_invoice_nl: ['invoice_number', 'invoice_date', 'company_name', 'total_amount'],
    str_invoice_en: ['invoice_number', 'invoice_date', 'company_name', 'total_amount'],
    btw_aangifte: ['period', 'year', 'quarter', 'btw_total'],
    aangifte_ib: ['year', 'administration', 'total_income', 'total_expenses'],
    toeristenbelasting: ['year', 'accommodation_name', 'total_nights', 'tourist_tax'],
    financial_report: ['year', 'administration', 'report_type'],
    zzp_invoice: ['invoice_number', 'invoice_date', 'company_name', 'grand_total', 'subtotal', 'lines'],
  };

  return placeholders[templateType] || [];
}

/**
 * Step Indicator Component
 */
interface StepIndicatorProps {
  number: number;
  label: string;
  isActive: boolean;
  isCompleted: boolean;
}

export const StepIndicator: React.FC<StepIndicatorProps> = ({ number, label, isActive, isCompleted }) => {
  const status = isCompleted ? 'completed' : isActive ? 'current' : 'upcoming';

  return (
    <VStack spacing={2}>
      <Box
        w="40px"
        h="40px"
        borderRadius="full"
        bg={isActive ? 'brand.orange' : isCompleted ? 'green.500' : 'gray.700'}
        color="white"
        display="flex"
        alignItems="center"
        justifyContent="center"
        fontWeight="bold"
        aria-label={`Step ${number}: ${label}, ${status}`}
      >
        {number}
      </Box>
      <Text
        fontSize="sm"
        color={isActive ? 'brand.orange' : 'gray.400'}
        fontWeight={isActive ? 'bold' : 'normal'}
        aria-hidden="true"
      >
        {label}
      </Text>
    </VStack>
  );
};
