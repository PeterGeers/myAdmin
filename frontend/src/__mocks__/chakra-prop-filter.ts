/**
 * Chakra UI Prop Filter Utility
 *
 * Separates Chakra-specific style/behavior props from standard HTML/DOM
 * attributes. Used by all mock components to prevent React DOM warnings
 * about unknown props in test output.
 */

/**
 * Set of all Chakra UI style and component-specific props that should be
 * stripped before passing to a DOM element. Using a Set for O(1) lookup.
 */
const CHAKRA_PROPS = new Set<string>([
  // Layout props
  'bg', 'p', 'px', 'py', 'pt', 'pb', 'pl', 'pr',
  'm', 'mx', 'my', 'mt', 'mb', 'ml', 'mr',
  'w', 'h', 'minH', 'maxH', 'minW', 'maxW',
  'display', 'alignItems', 'justifyContent', 'flexDirection', 'flex',
  'position', 'top', 'left', 'right', 'bottom', 'zIndex', 'overflow',
  'gap', 'spacing', 'flexWrap', 'flexGrow', 'flexShrink',
  'gridTemplateColumns', 'gridColumn', 'gridRow',

  // Styling props
  'colorScheme', 'variant', 'size',
  'borderRadius', 'boxShadow', 'border', 'borderColor', 'borderWidth',
  'borderTop', 'borderBottom',
  'textAlign', 'fontSize', 'fontWeight', 'fontFamily',
  'color', 'lineHeight', 'letterSpacing', 'textTransform', 'textDecoration',
  'opacity', 'cursor', 'transition', 'transform',
  'bgColor', 'background', 'backgroundImage',

  // Pseudo-style props
  '_hover', '_focus', '_active', '_disabled', '_selected',
  '_checked', '_expanded', '_grabbed', '_pressed',
  '_invalid', '_loading', '_placeholder',

  // Component-specific props
  'isDisabled', 'isLoading', 'loadingText', 'isInvalid', 'isRequired', 'isReadOnly',
  'isChecked', 'isOpen', 'onClose', 'onOpen', 'onToggle',
  'leftIcon', 'rightIcon',
  'templateColumns', 'colSpan', 'rowSpan',
  'animateOpacity', 'allowMultiple', 'defaultIndex',
  'scrollBehavior', 'leastDestructiveRef',
  'isTruncated', 'noOfLines',
  'isIndeterminate', 'hasStripe', 'isAnimated',
  'placement', 'gutter', 'arrowSize', 'arrowShadowColor',
  'motionPreset', 'preserveScrollBarGap', 'blockScrollOnMount',
  'closeOnOverlayClick', 'closeOnEsc', 'returnFocusOnClose',
  'autoFocus', 'trapFocus', 'initialFocusRef', 'finalFocusRef',
  'isLazy', 'lazyBehavior',
  'colorMode', 'useSystemColorMode', 'cssVarsRoot',
  'direction', 'environment', 'disableGlobalStyle',

  // Shorthand/internal props
  'as', 'sx', '__css', 'boxSize',

  // Additional style props that may leak through
  'minHeight', 'maxHeight', 'minWidth', 'maxWidth',
  'whiteSpace', 'overflowX', 'overflowY', 'resize',
  'fontStyle', 'wordBreak', 'textOverflow',

  // Additional layout/grid props
  'columns', 'minChildWidth', 'wrap', 'align', 'justify',
  'templateRows', 'autoFlow', 'autoColumns', 'autoRows',
  'isAttached', 'labelColor', 'isNumeric',
]);

/**
 * Filters out Chakra-specific props, returning only valid DOM attributes.
 *
 * @param props - The full props object from a Chakra component mock
 * @returns An object containing only standard HTML/DOM attributes
 */
export function filterChakraProps(
  props: Record<string, any>,
): Record<string, any> {
  const domProps: Record<string, any> = {};
  for (const key in props) {
    if (!CHAKRA_PROPS.has(key)) {
      domProps[key] = props[key];
    }
  }
  return domProps;
}
