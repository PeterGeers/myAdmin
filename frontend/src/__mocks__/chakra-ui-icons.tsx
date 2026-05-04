/**
 * Centralized Chakra UI Icons Mock Module
 *
 * Provides lightweight span-based mock implementations for all @chakra-ui/icons
 * exports. Loaded via resolve.alias in vite.config.ts test block.
 *
 * Uses <span> elements (not SVG) for simplicity and consistency with the
 * main Chakra mock module.
 */
import React from 'react';
import { filterChakraProps } from './chakra-prop-filter';

/**
 * Factory that creates a mock icon component rendering a <span> with
 * a data-testid matching the icon name.
 */
const createMockIcon = (name: string) => {
  const Icon = (props: any) => (
    <span data-testid={name} {...filterChakraProps(props)} />
  );
  Icon.displayName = name;
  return Icon;
};

// Icons from Requirement 2.1
export const CheckIcon = createMockIcon('CheckIcon');
export const CloseIcon = createMockIcon('CloseIcon');
export const WarningIcon = createMockIcon('WarningIcon');
export const InfoIcon = createMockIcon('InfoIcon');
export const CheckCircleIcon = createMockIcon('CheckCircleIcon');
export const SearchIcon = createMockIcon('SearchIcon');
export const ChevronDownIcon = createMockIcon('ChevronDownIcon');
export const ChevronUpIcon = createMockIcon('ChevronUpIcon');
export const ViewIcon = createMockIcon('ViewIcon');
export const ViewOffIcon = createMockIcon('ViewOffIcon');
export const ArrowUpIcon = createMockIcon('ArrowUpIcon');
export const ArrowDownIcon = createMockIcon('ArrowDownIcon');
export const AddIcon = createMockIcon('AddIcon');
export const DeleteIcon = createMockIcon('DeleteIcon');
export const EditIcon = createMockIcon('EditIcon');
export const ExternalLinkIcon = createMockIcon('ExternalLinkIcon');
export const DownloadIcon = createMockIcon('DownloadIcon');
export const HamburgerIcon = createMockIcon('HamburgerIcon');

// Backward-compatible icons from existing @chakra-ui/icons.tsx mock
export const ArrowBackIcon = createMockIcon('ArrowBackIcon');
export const ArrowForwardIcon = createMockIcon('ArrowForwardIcon');
export const ChevronLeftIcon = createMockIcon('ChevronLeftIcon');
export const ChevronRightIcon = createMockIcon('ChevronRightIcon');
export const CopyIcon = createMockIcon('CopyIcon');
export const InfoOutlineIcon = createMockIcon('InfoOutlineIcon');
export const LockIcon = createMockIcon('LockIcon');
export const MinusIcon = createMockIcon('MinusIcon');
export const MoonIcon = createMockIcon('MoonIcon');
export const RepeatIcon = createMockIcon('RepeatIcon');
export const Search2Icon = createMockIcon('Search2Icon');
export const SettingsIcon = createMockIcon('SettingsIcon');
export const SmallAddIcon = createMockIcon('SmallAddIcon');
export const SmallCloseIcon = createMockIcon('SmallCloseIcon');
export const SpinnerIcon = createMockIcon('SpinnerIcon');
export const StarIcon = createMockIcon('StarIcon');
export const SunIcon = createMockIcon('SunIcon');
export const TimeIcon = createMockIcon('TimeIcon');
export const TriangleDownIcon = createMockIcon('TriangleDownIcon');
export const TriangleUpIcon = createMockIcon('TriangleUpIcon');
export const UnlockIcon = createMockIcon('UnlockIcon');
export const WarningTwoIcon = createMockIcon('WarningTwoIcon');

// Factory export for direct usage
export const createIcon = (config: any) =>
  createMockIcon(config?.displayName || 'Icon');
