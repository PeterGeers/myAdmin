/**
 * Trip Import Stepper component — visual progress indicator for the import wizard.
 * Shows numbered steps with connecting lines, color-coded by completion state.
 * Reference: .kiro/specs/ZZP/rittenregistratie/design.md
 */

import React from 'react';
import { HStack, Box, Text, Flex } from '@chakra-ui/react';

interface TripImportStepperProps {
  currentStep: number;
  steps: string[];
}

export const TripImportStepper: React.FC<TripImportStepperProps> = ({ currentStep, steps }) => {
  return (
    <HStack spacing={0} w="100%" justify="center" py={4}>
      {steps.map((label, index) => {
        const isCompleted = index < currentStep;
        const isCurrent = index === currentStep;

        // Determine colors
        const circleBg = isCompleted ? 'green.400' : isCurrent ? 'orange.400' : 'gray.600';
        const circleColor = isCompleted || isCurrent ? 'white' : 'gray.400';
        const labelColor = isCurrent ? 'orange.300' : isCompleted ? 'green.300' : 'gray.500';
        const lineColor = isCompleted ? 'green.400' : 'gray.600';

        return (
          <Flex key={index} align="center" flex={index < steps.length - 1 ? 1 : undefined}>
            {/* Step circle + label */}
            <Flex direction="column" align="center" minW="80px">
              <Box
                w="36px"
                h="36px"
                borderRadius="full"
                bg={circleBg}
                color={circleColor}
                display="flex"
                alignItems="center"
                justifyContent="center"
                fontWeight="bold"
                fontSize="sm"
                border={isCurrent ? '2px solid' : 'none'}
                borderColor={isCurrent ? 'orange.300' : 'transparent'}
              >
                {isCompleted ? '✓' : index + 1}
              </Box>
              <Text
                fontSize="xs"
                color={labelColor}
                mt={1}
                fontWeight={isCurrent ? 'bold' : 'normal'}
                textAlign="center"
              >
                {label}
              </Text>
            </Flex>

            {/* Connecting line (not after last step) */}
            {index < steps.length - 1 && (
              <Box flex={1} h="2px" bg={lineColor} mx={2} mt="-18px" />
            )}
          </Flex>
        );
      })}
    </HStack>
  );
};

export default TripImportStepper;
