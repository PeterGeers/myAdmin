/**
 * Block type definitions and layout variant mappings.
 *
 * Central source of truth for available block types, their icons,
 * default layouts, and module requirements.
 */

export interface BlockTypeDefinition {
  type: string;
  icon: string;
  defaultLayout: string;
  layouts: string[];
  /** If set, block only appears when tenant has this module active */
  requiresModule?: string;
}

export const BLOCK_TYPE_DEFINITIONS: BlockTypeDefinition[] = [
  {
    type: 'hero',
    icon: '🖼️',
    defaultLayout: 'image-right',
    layouts: ['image-right', 'image-left', 'image-background', 'centered'],
  },
  {
    type: 'about',
    icon: '📝',
    defaultLayout: 'centered',
    layouts: ['centered', 'image-left', 'image-right'],
  },
  {
    type: 'gallery',
    icon: '🎨',
    defaultLayout: 'grid-3',
    layouts: ['grid-3', 'grid-4', 'masonry'],
  },
  {
    type: 'testimonials',
    icon: '💬',
    defaultLayout: 'cards',
    layouts: ['cards', 'slider'],
  },
  {
    type: 'faq',
    icon: '❓',
    defaultLayout: 'accordion',
    layouts: ['accordion', 'list'],
  },
  {
    type: 'pricing',
    icon: '💰',
    defaultLayout: 'cards',
    layouts: ['table', 'cards'],
  },
  {
    type: 'cta',
    icon: '📢',
    defaultLayout: 'centered',
    layouts: ['centered', 'left-aligned'],
  },
  {
    type: 'embed',
    icon: '🔗',
    defaultLayout: 'full-width',
    layouts: ['full-width', 'contained'],
  },
  {
    type: 'contact',
    icon: '✉️',
    defaultLayout: 'centered',
    layouts: ['centered'],
  },
  {
    type: 'services',
    icon: '🛠️',
    defaultLayout: 'grid-3',
    layouts: ['grid-3'],
    requiresModule: 'ZZP',
  },
];

/**
 * Get available layout variants for a given block type.
 */
export function getLayoutsForType(type: string): string[] {
  const def = BLOCK_TYPE_DEFINITIONS.find(bt => bt.type === type);
  return def?.layouts || [];
}
