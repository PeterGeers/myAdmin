# Implementation Plan

- [x] 1. Create the UnifiedAdminYearFilter component structure

  - Create new component file `frontend/src/components/UnifiedAdminYearFilter.tsx`
  - Define TypeScript interfaces for component props and state
  - Set up basic component structure with administration and year sections
  - Implement responsive layout using Chakra UI Grid system
  - _Requirements: 1.1, 3.1, 3.5_

- [x] 1.1 Write property test for component rendering consistency

  - **Property 1: Component Rendering Consistency**
  - **Validates: Requirements 1.1, 1.2, 4.1, 4.4**

- [x] 2. Implement administration filter section

  - Create administration dropdown using Chakra UI Select component
  - Implement administration option rendering with proper styling
  - Add administration change handler with callback integration
  - Apply consistent theming (gray backgrounds, white text, orange accents)
  - _Requirements: 2.1, 4.1_

- [x] 2.1 Write property test for selection behavior correctness

  - **Property 3: Selection Behavior Correctness**
  - **Validates: Requirements 2.1, 2.2, 2.3, 4.3**

- [x] 3. Implement year filter section with multi-select functionality

  - Create year multi-select using Chakra UI Menu and Checkbox components
  - Implement year selection state management for multiple selections
  - Add year change handler with array-based callback integration
  - Display selected years in button text (e.g., "2024, 2025")
  - _Requirements: 2.2, 2.3, 4.3_

- [x] 4. Add single-select year mode for BTW-style filters

  - Implement conditional rendering for single vs multi-select year mode
  - Create single-select year dropdown using Select component
  - Add prop to control multi-select vs single-select behavior
  - _Requirements: 2.2, 3.1_

- [x] 4.1 Write property test for state management and API consistency

  - **Property 2: State Management and API Consistency**
  - **Validates: Requirements 1.3, 1.4, 2.4, 2.5, 3.4**

- [x] 5. Implement configuration adaptability and prop handling

  - Add props for showing/hiding administration and year sections
  - Implement size variants (sm, md, lg) for different contexts
  - Add loading and disabled state handling
  - Create prop validation and default value handling
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 5.1 Write property test for configuration adaptability

  - **Property 4: Configuration Adaptability**
  - **Validates: Requirements 3.1, 3.2, 3.3, 3.5**

- [x] 6. Add visual feedback and interaction states

  - Implement hover states for interactive elements
  - Add loading indicators and disabled state styling
  - Implement placeholder text for empty selections
  - Add proper focus management and accessibility attributes
  - _Requirements: 4.2, 4.4, 4.5_

- [x] 6.1 Write property test for interaction feedback consistency

  - **Property 6: Interaction Feedback Consistency**
  - **Validates: Requirements 4.2, 4.5**

- [x] 7. Implement error handling and edge cases

  - Add error boundary and graceful error handling
  - Implement validation for invalid selections
  - Handle empty options arrays with appropriate messaging
  - Add cleanup for component unmounting
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 7.1 Write property test for error handling robustness

  - **Property 5: Error Handling Robustness**
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [x] 8. Create filter state adapter utilities

  - Create adapter functions for actualsFilters integration
  - Create adapter functions for btwFilters integration
  - Create adapter functions for refAnalysisFilters integration
  - Create adapter functions for aangifteIbFilters integration
  - Add TypeScript types for all adapter functions
  - _Requirements: 3.2, 3.4_

- [x] 9. Checkpoint - Ensure all tests pass

  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Integrate unified filter into Actuals Dashboard tab

  - Replace existing separate filters in Actuals tab with unified component
  - Use actualsFilters adapter for state management
  - Verify data fetching continues to work correctly
  - Test multi-select year functionality
  - _Requirements: 1.1, 1.3, 2.4, 3.4_

- [x] 11. Integrate unified filter into BTW Declaration tab

  - Replace existing separate filters in BTW tab with unified component
  - Use btwFilters adapter for state management
  - Configure for single-select year mode
  - Verify BTW report generation continues to work
  - _Requirements: 1.1, 1.3, 2.4, 3.4_

- [x] 12. Integrate unified filter into Reference Analysis tab

  - Replace existing separate filters in Reference Analysis tab with unified component
  - Use refAnalysisFilters adapter for state management
  - Test multi-select year functionality
  - Verify reference analysis data fetching works correctly
  - _Requirements: 1.1, 1.3, 2.4, 3.4_

- [x] 13. Integrate unified filter into Aangifte IB tab

  - Replace existing separate filters in Aangifte IB tab with unified component
  - Use aangifteIbFilters adapter for state management
  - Configure for single-select year mode
  - Verify Aangifte IB data fetching continues to work
  - _Requirements: 1.1, 1.3, 2.4, 3.4_

- [x] 13.1 Write integration tests for all tab integrations

  - Create integration tests for Actuals Dashboard integration
  - Create integration tests for BTW Declaration integration
  - Create integration tests for Reference Analysis integration
  - Create integration tests for Aangifte IB integration
  - _Requirements: 1.5, 2.4, 3.4_

- [x] 14. Update BNB-related tabs (years-only integration)

  - Integrate unified filter into BNB Actuals tab (years section only)
  - Integrate unified filter into BNB Violins tab (years section only)
  - Configure to hide administration section for BNB tabs
  - Verify BNB data fetching continues to work correctly
  - _Requirements: 1.1, 3.1, 3.2_

- [x] 15. Final Checkpoint - Ensure all tests pass

  - Ensure all tests pass, ask the user if questions arise.

- [x] 15.1 Write unit tests for component functionality

  - Create unit tests for component rendering
  - Create unit tests for event handling
  - Create unit tests for state management
  - Create unit tests for accessibility compliance
  - _Requirements: All requirements_
