/**
 * Jest mock for @chakra-ui/icons
 * 
 * Provides simple React component stubs for all Chakra UI icons.
 * Needed because Jest CJS resolution can't handle createIcon from @chakra-ui/react.
 */
import React from 'react';

const createMockIcon = (name: string) => {
  const Icon = (props: any) => React.createElement('svg', { 'data-testid': `${name}`, ...props });
  Icon.displayName = name;
  return Icon;
};

// Export all commonly used icons as simple SVG stubs
export const AddIcon = createMockIcon('AddIcon');
export const ArrowBackIcon = createMockIcon('ArrowBackIcon');
export const ArrowForwardIcon = createMockIcon('ArrowForwardIcon');
export const CheckCircleIcon = createMockIcon('CheckCircleIcon');
export const CheckIcon = createMockIcon('CheckIcon');
export const ChevronDownIcon = createMockIcon('ChevronDownIcon');
export const ChevronLeftIcon = createMockIcon('ChevronLeftIcon');
export const ChevronRightIcon = createMockIcon('ChevronRightIcon');
export const ChevronUpIcon = createMockIcon('ChevronUpIcon');
export const CloseIcon = createMockIcon('CloseIcon');
export const CopyIcon = createMockIcon('CopyIcon');
export const DeleteIcon = createMockIcon('DeleteIcon');
export const DownloadIcon = createMockIcon('DownloadIcon');
export const EditIcon = createMockIcon('EditIcon');
export const ExternalLinkIcon = createMockIcon('ExternalLinkIcon');
export const HamburgerIcon = createMockIcon('HamburgerIcon');
export const InfoIcon = createMockIcon('InfoIcon');
export const InfoOutlineIcon = createMockIcon('InfoOutlineIcon');
export const LockIcon = createMockIcon('LockIcon');
export const MinusIcon = createMockIcon('MinusIcon');
export const MoonIcon = createMockIcon('MoonIcon');
export const RepeatIcon = createMockIcon('RepeatIcon');
export const SearchIcon = createMockIcon('SearchIcon');
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
export const ViewIcon = createMockIcon('ViewIcon');
export const ViewOffIcon = createMockIcon('ViewOffIcon');
export const WarningIcon = createMockIcon('WarningIcon');
export const WarningTwoIcon = createMockIcon('WarningTwoIcon');

// Also export createIcon for any direct usage
export const createIcon = (config: any) => createMockIcon(config.displayName || 'Icon');
