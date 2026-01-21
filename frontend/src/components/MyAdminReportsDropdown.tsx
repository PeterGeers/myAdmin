import React, { useState } from 'react';
import {
  Box,
  HStack,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Button,
  Text,
  VStack,
} from '@chakra-ui/react';
import { ChevronDownIcon } from '@chakra-ui/icons';
import MyAdminReports from './myAdminReports';

// Report categories
type Category = 'bnb' | 'financial';

const categories = {
  bnb: { label: '🏠 BNB Reports', color: 'blue' },
  financial: { label: '💰 Financial Reports', color: 'green' },
};

// Report definitions
const reports = {
  bnb: [
    { id: 'bnb-revenue', label: 'BNB Revenue', icon: '🏠', tabIndex: 1 },
    { id: 'bnb-actuals', label: 'BNB Actuals', icon: '🏡', tabIndex: 3 },
    { id: 'bnb-violins', label: 'BNB Violins', icon: '🎻', tabIndex: 7 },
    { id: 'bnb-returning', label: 'BNB Terugkerend', icon: '🔄', tabIndex: 8 },
    { id: 'bnb-future', label: 'BNB Future', icon: '📈', tabIndex: 9 },
    { id: 'toeristenbelasting', label: 'Toeristenbelasting', icon: '🏨', tabIndex: 5 },
  ],
  financial: [
    { id: 'mutaties', label: 'Mutaties (P&L)', icon: '💰', tabIndex: 0 },
    { id: 'actuals', label: 'Actuals', icon: '📊', tabIndex: 2 },
    { id: 'btw', label: 'BTW aangifte', icon: '🧾', tabIndex: 4 },
    { id: 'reference', label: 'View ReferenceNumber', icon: '📈', tabIndex: 6 },
    { id: 'aangifte-ib', label: 'Aangifte IB', icon: '📋', tabIndex: 10 },
  ],
};

const MyAdminReportsDropdown: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<Category>('bnb');
  const [selectedReport, setSelectedReport] = useState(reports.bnb[0]);

  const handleCategorySelect = (category: Category) => {
    setSelectedCategory(category);
    // Auto-select first report in the new category
    setSelectedReport(reports[category][0]);
  };

  const handleReportSelect = (report: typeof reports.bnb[0]) => {
    setSelectedReport(report);
  };

  const currentReports = reports[selectedCategory];

  return (
    <Box p={6} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        {/* Two-Level Selector */}
        <Box bg="gray.700" p={4} borderRadius="md">
          <HStack spacing={4} align="center" wrap="wrap">
            {/* Category Selector */}
            <VStack align="start" spacing={1}>
              <Text color="gray.400" fontSize="sm">
                Category:
              </Text>
              <Menu>
                <MenuButton
                  as={Button}
                  rightIcon={<ChevronDownIcon />}
                  bg="orange.500"
                  color="white"
                  _hover={{ bg: 'orange.600' }}
                  _active={{ bg: 'orange.600' }}
                  size="md"
                  minW="200px"
                >
                  {categories[selectedCategory].label}
                </MenuButton>
                <MenuList bg="gray.700" borderColor="gray.600">
                  <MenuItem
                    onClick={() => handleCategorySelect('bnb')}
                    bg={selectedCategory === 'bnb' ? 'orange.600' : 'gray.700'}
                    _hover={{ bg: 'orange.500' }}
                    color="white"
                  >
                    {categories.bnb.label}
                  </MenuItem>
                  <MenuItem
                    onClick={() => handleCategorySelect('financial')}
                    bg={selectedCategory === 'financial' ? 'orange.600' : 'gray.700'}
                    _hover={{ bg: 'orange.500' }}
                    color="white"
                  >
                    {categories.financial.label}
                  </MenuItem>
                </MenuList>
              </Menu>
            </VStack>

            {/* Report Selector */}
            <VStack align="start" spacing={1}>
              <Text color="gray.400" fontSize="sm">
                Report:
              </Text>
              <Menu>
                <MenuButton
                  as={Button}
                  rightIcon={<ChevronDownIcon />}
                  bg="blue.500"
                  color="white"
                  _hover={{ bg: 'blue.600' }}
                  _active={{ bg: 'blue.600' }}
                  size="md"
                  minW="250px"
                >
                  {selectedReport.icon} {selectedReport.label}
                </MenuButton>
                <MenuList bg="gray.700" borderColor="gray.600" maxH="400px" overflowY="auto">
                  {currentReports.map((report) => (
                    <MenuItem
                      key={report.id}
                      onClick={() => handleReportSelect(report)}
                      bg={selectedReport.id === report.id ? 'blue.600' : 'gray.700'}
                      _hover={{ bg: 'blue.500' }}
                      color="white"
                    >
                      {report.icon} {report.label}
                    </MenuItem>
                  ))}
                </MenuList>
              </Menu>
            </VStack>
          </HStack>
        </Box>

        {/* Report Content */}
        <Box key={selectedReport.id}>
          <MyAdminReports defaultTabIndex={selectedReport.tabIndex} hideTabList={true} />
        </Box>
      </VStack>
    </Box>
  );
};

export default MyAdminReportsDropdown;
