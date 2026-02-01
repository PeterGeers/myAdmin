/**
 * Field Mapping Editor Component
 * 
 * JSON editor for customizing field mappings in templates.
 * Includes validation, help text, and examples.
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  VStack,
  HStack,
  FormControl,
  FormLabel,
  FormErrorMessage,
  FormHelperText,
  Textarea,
  Button,
  Text,
  Code,
  Collapse,
  useDisclosure,
  Alert,
  AlertIcon,
  AlertDescription,
  Divider,
} from '@chakra-ui/react';
import { TemplateType } from '../../../services/templateApi';

/**
 * Component props
 */
interface FieldMappingEditorProps {
  value: Record<string, any>;
  onChange: (value: Record<string, any>) => void;
  templateType?: TemplateType;
  disabled?: boolean;
}

/**
 * Example mappings for different template types
 */
const EXAMPLE_MAPPINGS: Record<TemplateType, Record<string, any>> = {
  str_invoice_nl: {
    company_name: 'Mijn Bedrijf BV',
    company_address: 'Hoofdstraat 123',
    company_city: 'Amsterdam',
    vat_number: 'NL123456789B01',
  },
  str_invoice_en: {
    company_name: 'My Company Ltd',
    company_address: '123 Main Street',
    company_city: 'London',
    vat_number: 'GB123456789',
  },
  btw_aangifte: {
    period_label: 'Kwartaal',
    currency_symbol: '€',
    decimal_separator: ',',
  },
  aangifte_ib: {
    tax_year_label: 'Belastingjaar',
    currency_format: '€ #,##0.00',
  },
  toeristenbelasting: {
    municipality: 'Amsterdam',
    tax_rate: '7%',
    contact_email: 'info@example.com',
  },
  financial_report: {
    report_title: 'Financieel Overzicht',
    currency: 'EUR',
    date_format: 'DD-MM-YYYY',
  },
};

/**
 * FieldMappingEditor Component
 */
export const FieldMappingEditor: React.FC<FieldMappingEditorProps> = ({
  value,
  onChange,
  templateType,
  disabled = false,
}) => {
  const [jsonString, setJsonString] = useState<string>('');
  const [error, setError] = useState<string>('');
  const { isOpen: showHelp, onToggle: toggleHelp } = useDisclosure();
  const { isOpen: showExamples, onToggle: toggleExamples } = useDisclosure();

  /**
   * Initialize JSON string from value
   */
  useEffect(() => {
    try {
      setJsonString(JSON.stringify(value, null, 2));
    } catch {
      setJsonString('{}');
    }
  }, [value]);

  /**
   * Validate and parse JSON
   */
  const validateAndParse = (text: string): boolean => {
    // Empty or whitespace-only is valid (uses defaults)
    if (!text.trim() || text.trim() === '{}') {
      setError('');
      onChange({});
      return true;
    }

    try {
      const parsed = JSON.parse(text);
      
      // Ensure it's an object
      if (typeof parsed !== 'object' || Array.isArray(parsed)) {
        setError('Field mappings must be a JSON object, not an array or primitive');
        return false;
      }

      setError('');
      onChange(parsed);
      return true;
    } catch (err) {
      if (err instanceof Error) {
        setError(`Invalid JSON: ${err.message}`);
      } else {
        setError('Invalid JSON format');
      }
      return false;
    }
  };

  /**
   * Handle text change
   */
  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = event.target.value;
    setJsonString(newValue);
    validateAndParse(newValue);
  };

  /**
   * Format JSON (prettify)
   */
  const handleFormat = () => {
    try {
      const parsed = JSON.parse(jsonString);
      const formatted = JSON.stringify(parsed, null, 2);
      setJsonString(formatted);
      setError('');
      onChange(parsed);
    } catch {
      // If parsing fails, validation error is already shown
    }
  };

  /**
   * Reset to empty
   */
  const handleReset = () => {
    setJsonString('{}');
    setError('');
    onChange({});
  };

  /**
   * Load example for current template type
   */
  const handleLoadExample = () => {
    if (templateType && EXAMPLE_MAPPINGS[templateType]) {
      const example = EXAMPLE_MAPPINGS[templateType];
      const formatted = JSON.stringify(example, null, 2);
      setJsonString(formatted);
      setError('');
      onChange(example);
    }
  };

  return (
    <VStack spacing={4} align="stretch">
      {/* Info Alert */}
      <Alert status="info" bg="blue.900" borderRadius="md">
        <AlertIcon />
        <AlertDescription fontSize="sm">
          Field mappings are optional. Leave empty to use default values from your data.
          Use this to override specific fields or add custom values.
        </AlertDescription>
      </Alert>

      {/* Editor */}
      <FormControl isInvalid={!!error}>
        <FormLabel>Field Mappings (JSON)</FormLabel>
        <Textarea
          value={jsonString}
          onChange={handleChange}
          placeholder='{\n  "field_name": "custom_value",\n  "another_field": "another_value"\n}'
          rows={12}
          fontFamily="monospace"
          fontSize="sm"
          isDisabled={disabled}
          bg="gray.800"
          borderColor={error ? 'red.500' : 'gray.600'}
          _focus={{
            borderColor: error ? 'red.500' : 'brand.orange',
            boxShadow: error ? '0 0 0 1px red' : '0 0 0 1px #ff6600',
          }}
        />
        {error && <FormErrorMessage>{error}</FormErrorMessage>}
        <FormHelperText color="gray.400" fontSize="xs">
          Enter field mappings as JSON. Use the buttons below for help.
        </FormHelperText>
      </FormControl>

      {/* Action Buttons */}
      <HStack spacing={2} wrap="wrap">
        <Button
          size="sm"
          onClick={handleFormat}
          isDisabled={disabled || !!error}
          variant="outline"
        >
          Format JSON
        </Button>
        <Button
          size="sm"
          onClick={handleReset}
          isDisabled={disabled}
          variant="outline"
        >
          Reset
        </Button>
        {templateType && (
          <Button
            size="sm"
            onClick={handleLoadExample}
            isDisabled={disabled}
            colorScheme="blue"
          >
            Load Example
          </Button>
        )}
        <Button
          size="sm"
          onClick={toggleHelp}
          variant="ghost"
        >
          {showHelp ? 'Hide' : 'Show'} Help
        </Button>
        <Button
          size="sm"
          onClick={toggleExamples}
          variant="ghost"
        >
          {showExamples ? 'Hide' : 'Show'} Examples
        </Button>
      </HStack>

      {/* Help Section */}
      <Collapse in={showHelp} animateOpacity>
        <Box bg="gray.800" p={4} borderRadius="md">
          <Text fontWeight="bold" mb={2}>
            📖 How to Use Field Mappings
          </Text>
          <VStack align="start" spacing={2} fontSize="sm" color="gray.300">
            <Text>
              • Field mappings allow you to customize values in your template
            </Text>
            <Text>
              • Use JSON format: <Code>{"{ \"field\": \"value\" }"}</Code>
            </Text>
            <Text>
              • Keys should match placeholder names in your template
            </Text>
            <Text>
              • Values can be strings, numbers, or booleans
            </Text>
            <Text>
              • Leave empty to use default values from your data
            </Text>
          </VStack>
        </Box>
      </Collapse>

      {/* Examples Section */}
      <Collapse in={showExamples} animateOpacity>
        <Box bg="gray.800" p={4} borderRadius="md">
          <Text fontWeight="bold" mb={3}>
            💡 Example Field Mappings
          </Text>
          
          <VStack align="stretch" spacing={3} divider={<Divider borderColor="gray.700" />}>
            {/* Basic Example */}
            <Box>
              <Text fontSize="sm" fontWeight="bold" mb={1}>
                Basic Override:
              </Text>
              <Code
                display="block"
                whiteSpace="pre"
                p={2}
                bg="gray.900"
                borderRadius="md"
                fontSize="xs"
              >
                {`{
  "company_name": "My Custom Company",
  "vat_number": "NL123456789B01"
}`}
              </Code>
            </Box>

            {/* Formatting Example */}
            <Box>
              <Text fontSize="sm" fontWeight="bold" mb={1}>
                Custom Formatting:
              </Text>
              <Code
                display="block"
                whiteSpace="pre"
                p={2}
                bg="gray.900"
                borderRadius="md"
                fontSize="xs"
              >
                {`{
  "currency_symbol": "€",
  "date_format": "DD-MM-YYYY",
  "decimal_separator": ","
}`}
              </Code>
            </Box>

            {/* Template-Specific Example */}
            {templateType && EXAMPLE_MAPPINGS[templateType] && (
              <Box>
                <Text fontSize="sm" fontWeight="bold" mb={1}>
                  Example for {templateType}:
                </Text>
                <Code
                  display="block"
                  whiteSpace="pre"
                  p={2}
                  bg="gray.900"
                  borderRadius="md"
                  fontSize="xs"
                >
                  {JSON.stringify(EXAMPLE_MAPPINGS[templateType], null, 2)}
                </Code>
              </Box>
            )}
          </VStack>
        </Box>
      </Collapse>
    </VStack>
  );
};

export default FieldMappingEditor;
