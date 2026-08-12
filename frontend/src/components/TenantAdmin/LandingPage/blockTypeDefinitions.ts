/**
 * Block type definitions and layout variant mappings.
 *
 * Central source of truth for available block types, their icons,
 * default layouts, and module requirements.
 */

export interface LayoutOption {
  id: string;
  label: string;
  /** Small inline SVG thumbnail (~40x30 viewBox) showing layout structure */
  thumbnail: string;
}

export interface BlockTypeDefinition {
  type: string;
  icon: string;
  defaultLayout: string;
  layouts: LayoutOption[];
  /** If set, block only appears when tenant has this module active */
  requiresModule?: string;
}

// ============================================================================
// SVG Thumbnails — schematic representations of layout structures
// ============================================================================

const SVG_THUMBNAILS = {
  // Hero layouts
  heroDefault: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="8" width="14" height="2" fill="#333"/><rect x="3" y="12" width="12" height="1.5" fill="#999"/><rect x="3" y="15" width="10" height="1.5" fill="#999"/><rect x="3" y="20" width="8" height="3" rx="1" fill="#4A90D9"/><rect x="22" y="4" width="15" height="22" rx="2" fill="#ddd"/></svg>`,
  heroImageLeft: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="4" width="15" height="22" rx="2" fill="#ddd"/><rect x="22" y="8" width="14" height="2" fill="#333"/><rect x="22" y="12" width="12" height="1.5" fill="#999"/><rect x="22" y="15" width="10" height="1.5" fill="#999"/><rect x="22" y="20" width="8" height="3" rx="1" fill="#4A90D9"/></svg>`,
  heroImageBg: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#666" stroke="#ccc"/><rect x="8" y="10" width="24" height="2" fill="#fff"/><rect x="10" y="14" width="20" height="1.5" fill="#ddd"/><rect x="14" y="20" width="12" height="3" rx="1" fill="#4A90D9"/></svg>`,
  heroSplitDiagonal: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><polygon points="18,1 39,1 39,29 8,29" fill="#ddd"/><rect x="3" y="10" width="12" height="2" fill="#333"/><rect x="3" y="14" width="10" height="1.5" fill="#999"/><rect x="3" y="20" width="8" height="3" rx="1" fill="#4A90D9"/></svg>`,
  heroVideoBg: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#333" stroke="#ccc"/><polygon points="17,11 17,19 25,15" fill="#fff"/><rect x="10" y="22" width="20" height="2" fill="#fff" opacity="0.7"/><rect x="12" y="25" width="16" height="1.5" fill="#fff" opacity="0.5"/></svg>`,

  // About layouts
  aboutDefault: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="5" width="16" height="2" fill="#333"/><rect x="3" y="9" width="20" height="1.2" fill="#999"/><rect x="3" y="12" width="18" height="1.2" fill="#999"/><rect x="3" y="15" width="19" height="1.2" fill="#999"/><rect x="26" y="5" width="11" height="20" rx="2" fill="#ddd"/></svg>`,
  aboutImageLeft: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="5" width="11" height="20" rx="2" fill="#ddd"/><rect x="17" y="5" width="16" height="2" fill="#333"/><rect x="17" y="9" width="20" height="1.2" fill="#999"/><rect x="17" y="12" width="18" height="1.2" fill="#999"/><rect x="17" y="15" width="19" height="1.2" fill="#999"/></svg>`,
  aboutImageRight: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="5" width="16" height="2" fill="#333"/><rect x="3" y="9" width="20" height="1.2" fill="#999"/><rect x="3" y="12" width="18" height="1.2" fill="#999"/><rect x="26" y="5" width="11" height="20" rx="2" fill="#ddd"/></svg>`,
  aboutCard: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f0f0f0" stroke="#ccc"/><rect x="8" y="5" width="24" height="20" rx="3" fill="#fff" stroke="#ddd"/><rect x="12" y="9" width="16" height="2" fill="#333"/><rect x="13" y="13" width="14" height="1.2" fill="#999"/><rect x="14" y="16" width="12" height="1.2" fill="#999"/></svg>`,
  aboutTimeline: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><line x1="10" y1="5" x2="10" y2="25" stroke="#4A90D9" stroke-width="1.5"/><circle cx="10" cy="8" r="2" fill="#4A90D9"/><rect x="14" y="7" width="12" height="1.5" fill="#333"/><circle cx="10" cy="16" r="2" fill="#4A90D9"/><rect x="14" y="15" width="14" height="1.5" fill="#333"/><circle cx="10" cy="24" r="2" fill="#4A90D9"/><rect x="14" y="23" width="10" height="1.5" fill="#333"/></svg>`,

  // Gallery layouts
  galleryGrid3: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="4" width="10" height="10" rx="1" fill="#ddd"/><rect x="15" y="4" width="10" height="10" rx="1" fill="#ddd"/><rect x="27" y="4" width="10" height="10" rx="1" fill="#ddd"/><rect x="3" y="17" width="10" height="10" rx="1" fill="#ddd"/><rect x="15" y="17" width="10" height="10" rx="1" fill="#ddd"/><rect x="27" y="17" width="10" height="10" rx="1" fill="#ddd"/></svg>`,
  galleryGrid4: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="4" width="7.5" height="10" rx="1" fill="#ddd"/><rect x="12" y="4" width="7.5" height="10" rx="1" fill="#ddd"/><rect x="21" y="4" width="7.5" height="10" rx="1" fill="#ddd"/><rect x="30" y="4" width="7.5" height="10" rx="1" fill="#ddd"/><rect x="3" y="17" width="7.5" height="10" rx="1" fill="#ddd"/><rect x="12" y="17" width="7.5" height="10" rx="1" fill="#ddd"/><rect x="21" y="17" width="7.5" height="10" rx="1" fill="#ddd"/><rect x="30" y="17" width="7.5" height="10" rx="1" fill="#ddd"/></svg>`,
  galleryMasonry: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="3" width="11" height="14" rx="1" fill="#ddd"/><rect x="3" y="19" width="11" height="8" rx="1" fill="#ddd"/><rect x="16" y="3" width="11" height="8" rx="1" fill="#ddd"/><rect x="16" y="13" width="11" height="14" rx="1" fill="#ddd"/><rect x="29" y="3" width="8" height="11" rx="1" fill="#ddd"/><rect x="29" y="16" width="8" height="11" rx="1" fill="#ddd"/></svg>`,
  galleryCarousel: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="6" y="5" width="28" height="18" rx="2" fill="#ddd"/><polygon points="3,14 5,12 5,16" fill="#999"/><polygon points="37,14 35,12 35,16" fill="#999"/><circle cx="17" cy="26" r="1.2" fill="#4A90D9"/><circle cx="20" cy="26" r="1.2" fill="#ccc"/><circle cx="23" cy="26" r="1.2" fill="#ccc"/></svg>`,

  // Testimonials layouts
  testimonialsCards: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="4" width="10" height="22" rx="2" fill="#fff" stroke="#ddd"/><rect x="15" y="4" width="10" height="22" rx="2" fill="#fff" stroke="#ddd"/><rect x="27" y="4" width="10" height="22" rx="2" fill="#fff" stroke="#ddd"/><rect x="5" y="7" width="6" height="1" fill="#999"/><rect x="17" y="7" width="6" height="1" fill="#999"/><rect x="29" y="7" width="6" height="1" fill="#999"/></svg>`,
  testimonialsCarousel: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="8" y="5" width="24" height="18" rx="2" fill="#fff" stroke="#ddd"/><rect x="12" y="9" width="16" height="1.5" fill="#999"/><rect x="13" y="12" width="14" height="1.2" fill="#ccc"/><polygon points="4,14 6,12 6,16" fill="#999"/><polygon points="36,14 34,12 34,16" fill="#999"/><circle cx="18" cy="26" r="1.2" fill="#4A90D9"/><circle cx="20" cy="26" r="1.2" fill="#ccc"/><circle cx="22" cy="26" r="1.2" fill="#ccc"/></svg>`,
  testimonialsQuoteLarge: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><text x="8" y="14" font-size="10" fill="#4A90D9" font-family="serif">"</text><rect x="14" y="10" width="20" height="2" fill="#333"/><rect x="16" y="14" width="16" height="1.5" fill="#999"/><rect x="18" y="20" width="10" height="1.2" fill="#666"/></svg>`,
  testimonialsGrid: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="4" width="16" height="10" fill="#fff" stroke="#eee"/><rect x="21" y="4" width="16" height="10" fill="#fff" stroke="#eee"/><rect x="3" y="16" width="16" height="10" fill="#fff" stroke="#eee"/><rect x="21" y="16" width="16" height="10" fill="#fff" stroke="#eee"/></svg>`,

  // FAQ layouts
  faqDefault: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="4" y="5" width="32" height="4" rx="1" fill="#fff" stroke="#ddd"/><rect x="4" y="11" width="32" height="4" rx="1" fill="#fff" stroke="#ddd"/><rect x="4" y="17" width="32" height="4" rx="1" fill="#fff" stroke="#ddd"/><rect x="4" y="23" width="32" height="4" rx="1" fill="#fff" stroke="#ddd"/></svg>`,
  faqTwoColumn: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="5" width="15" height="3.5" rx="1" fill="#fff" stroke="#ddd"/><rect x="3" y="10" width="15" height="3.5" rx="1" fill="#fff" stroke="#ddd"/><rect x="3" y="15" width="15" height="3.5" rx="1" fill="#fff" stroke="#ddd"/><rect x="22" y="5" width="15" height="3.5" rx="1" fill="#fff" stroke="#ddd"/><rect x="22" y="10" width="15" height="3.5" rx="1" fill="#fff" stroke="#ddd"/><rect x="22" y="15" width="15" height="3.5" rx="1" fill="#fff" stroke="#ddd"/></svg>`,
  faqSideBySide: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="5" width="12" height="2" fill="#333"/><rect x="18" y="5" width="18" height="1.5" fill="#999"/><line x1="3" y1="10" x2="37" y2="10" stroke="#eee"/><rect x="3" y="12" width="12" height="2" fill="#333"/><rect x="18" y="12" width="18" height="1.5" fill="#999"/><line x1="3" y1="17" x2="37" y2="17" stroke="#eee"/><rect x="3" y="19" width="12" height="2" fill="#333"/><rect x="18" y="19" width="18" height="1.5" fill="#999"/></svg>`,

  // Pricing layouts
  pricingDefault: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="4" width="10" height="22" rx="2" fill="#fff" stroke="#ddd"/><rect x="15" y="4" width="10" height="22" rx="2" fill="#fff" stroke="#ddd"/><rect x="27" y="4" width="10" height="22" rx="2" fill="#fff" stroke="#ddd"/><rect x="5" y="7" width="6" height="2" fill="#333"/><rect x="17" y="7" width="6" height="2" fill="#333"/><rect x="29" y="7" width="6" height="2" fill="#333"/></svg>`,
  pricingHorizontal: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="4" width="34" height="6" rx="1" fill="#fff" stroke="#ddd"/><rect x="3" y="12" width="34" height="6" rx="1" fill="#fff" stroke="#ddd"/><rect x="3" y="20" width="34" height="6" rx="1" fill="#fff" stroke="#ddd"/></svg>`,
  pricingFeaturedCenter: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="7" width="9" height="18" rx="2" fill="#fff" stroke="#ddd"/><rect x="14" y="3" width="12" height="24" rx="2" fill="#4A90D9" stroke="#3A7BC8"/><rect x="28" y="7" width="9" height="18" rx="2" fill="#fff" stroke="#ddd"/></svg>`,
  pricingComparisonTable: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="3" width="34" height="4" fill="#eee"/><line x1="3" y1="9" x2="37" y2="9" stroke="#ddd"/><line x1="3" y1="14" x2="37" y2="14" stroke="#ddd"/><line x1="3" y1="19" x2="37" y2="19" stroke="#ddd"/><line x1="3" y1="24" x2="37" y2="24" stroke="#ddd"/><line x1="14" y1="3" x2="14" y2="27" stroke="#ddd"/><line x1="25" y1="3" x2="25" y2="27" stroke="#ddd"/></svg>`,

  // CTA layouts
  ctaDefault: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="10" y="8" width="20" height="2.5" fill="#333"/><rect x="12" y="13" width="16" height="1.5" fill="#999"/><rect x="14" y="19" width="12" height="4" rx="2" fill="#4A90D9"/></svg>`,
  ctaSplit: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="10" width="16" height="2.5" fill="#333"/><rect x="3" y="14" width="14" height="1.5" fill="#999"/><rect x="26" y="12" width="10" height="4" rx="2" fill="#4A90D9"/></svg>`,
  ctaBanner: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="2" y="11" width="36" height="8" rx="1" fill="#4A90D9" opacity="0.15"/><rect x="5" y="13" width="14" height="2" fill="#333"/><rect x="26" y="13" width="9" height="3.5" rx="1.5" fill="#4A90D9"/></svg>`,
  ctaFloating: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="3" y="5" width="34" height="1" fill="#eee"/><rect x="3" y="9" width="34" height="1" fill="#eee"/><rect x="3" y="13" width="34" height="1" fill="#eee"/><rect x="4" y="22" width="32" height="6" rx="3" fill="#4A90D9" opacity="0.9"/><rect x="12" y="24" width="16" height="2" rx="1" fill="#fff"/></svg>`,

  // Video layouts
  videoCentered: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="8" y="6" width="24" height="15" rx="2" fill="#333"/><polygon points="17,11 17,17 23,14" fill="#fff"/><rect x="14" y="24" width="12" height="1.5" fill="#999"/></svg>`,
  videoFullWidth: `<svg viewBox="0 0 40 30" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="38" height="28" rx="2" fill="#f5f5f5" stroke="#ccc"/><rect x="2" y="4" width="36" height="20" rx="1" fill="#333"/><polygon points="17,11 17,18 25,14.5" fill="#fff"/><rect x="12" y="26" width="16" height="1.5" fill="#999"/></svg>`,
} as const;

export const BLOCK_TYPE_DEFINITIONS: BlockTypeDefinition[] = [
  {
    type: 'hero',
    icon: '🖼️',
    defaultLayout: 'default',
    layouts: [
      { id: 'default', label: 'Default', thumbnail: SVG_THUMBNAILS.heroDefault },
      { id: 'image-left', label: 'Image Left', thumbnail: SVG_THUMBNAILS.heroImageLeft },
      { id: 'image-bg', label: 'Image Background', thumbnail: SVG_THUMBNAILS.heroImageBg },
      { id: 'split-diagonal', label: 'Split Diagonal', thumbnail: SVG_THUMBNAILS.heroSplitDiagonal },
      { id: 'video-bg', label: 'Video Background', thumbnail: SVG_THUMBNAILS.heroVideoBg },
    ],
  },
  {
    type: 'about',
    icon: '📝',
    defaultLayout: 'default',
    layouts: [
      { id: 'default', label: 'Default', thumbnail: SVG_THUMBNAILS.aboutDefault },
      { id: 'image-left', label: 'Image Left', thumbnail: SVG_THUMBNAILS.aboutImageLeft },
      { id: 'image-right', label: 'Image Right', thumbnail: SVG_THUMBNAILS.aboutImageRight },
      { id: 'card', label: 'Card', thumbnail: SVG_THUMBNAILS.aboutCard },
      { id: 'timeline', label: 'Timeline', thumbnail: SVG_THUMBNAILS.aboutTimeline },
    ],
  },
  {
    type: 'gallery',
    icon: '🎨',
    defaultLayout: 'grid-3',
    layouts: [
      { id: 'grid-3', label: 'Grid 3', thumbnail: SVG_THUMBNAILS.galleryGrid3 },
      { id: 'grid-4', label: 'Grid 4', thumbnail: SVG_THUMBNAILS.galleryGrid4 },
      { id: 'masonry', label: 'Masonry', thumbnail: SVG_THUMBNAILS.galleryMasonry },
      { id: 'carousel', label: 'Carousel', thumbnail: SVG_THUMBNAILS.galleryCarousel },
    ],
  },
  {
    type: 'testimonials',
    icon: '💬',
    defaultLayout: 'cards',
    layouts: [
      { id: 'cards', label: 'Cards', thumbnail: SVG_THUMBNAILS.testimonialsCards },
      { id: 'carousel', label: 'Carousel', thumbnail: SVG_THUMBNAILS.testimonialsCarousel },
      { id: 'quote-large', label: 'Large Quote', thumbnail: SVG_THUMBNAILS.testimonialsQuoteLarge },
      { id: 'grid', label: 'Grid', thumbnail: SVG_THUMBNAILS.testimonialsGrid },
    ],
  },
  {
    type: 'faq',
    icon: '❓',
    defaultLayout: 'default',
    layouts: [
      { id: 'default', label: 'Default', thumbnail: SVG_THUMBNAILS.faqDefault },
      { id: 'two-column', label: 'Two Column', thumbnail: SVG_THUMBNAILS.faqTwoColumn },
      { id: 'side-by-side', label: 'Side by Side', thumbnail: SVG_THUMBNAILS.faqSideBySide },
    ],
  },
  {
    type: 'pricing',
    icon: '💰',
    defaultLayout: 'default',
    layouts: [
      { id: 'default', label: 'Default', thumbnail: SVG_THUMBNAILS.pricingDefault },
      { id: 'horizontal', label: 'Horizontal', thumbnail: SVG_THUMBNAILS.pricingHorizontal },
      { id: 'featured-center', label: 'Featured Center', thumbnail: SVG_THUMBNAILS.pricingFeaturedCenter },
      { id: 'comparison-table', label: 'Comparison Table', thumbnail: SVG_THUMBNAILS.pricingComparisonTable },
    ],
  },
  {
    type: 'cta',
    icon: '📢',
    defaultLayout: 'default',
    layouts: [
      { id: 'default', label: 'Default', thumbnail: SVG_THUMBNAILS.ctaDefault },
      { id: 'split', label: 'Split', thumbnail: SVG_THUMBNAILS.ctaSplit },
      { id: 'banner', label: 'Banner', thumbnail: SVG_THUMBNAILS.ctaBanner },
      { id: 'floating', label: 'Floating', thumbnail: SVG_THUMBNAILS.ctaFloating },
    ],
  },
  {
    type: 'embed',
    icon: '🔗',
    defaultLayout: 'full-width',
    layouts: [
      { id: 'full-width', label: 'Full Width', thumbnail: SVG_THUMBNAILS.videoFullWidth },
      { id: 'contained', label: 'Contained', thumbnail: SVG_THUMBNAILS.videoCentered },
    ],
  },
  {
    type: 'contact',
    icon: '✉️',
    defaultLayout: 'centered',
    layouts: [
      { id: 'centered', label: 'Centered', thumbnail: SVG_THUMBNAILS.ctaDefault },
    ],
  },
  {
    type: 'services',
    icon: '🛠️',
    defaultLayout: 'grid-3',
    layouts: [
      { id: 'grid-3', label: 'Grid 3', thumbnail: SVG_THUMBNAILS.galleryGrid3 },
    ],
    requiresModule: 'ZZP',
  },
  {
    type: 'video',
    icon: '🎬',
    defaultLayout: 'centered',
    layouts: [
      { id: 'centered', label: 'Centered', thumbnail: SVG_THUMBNAILS.videoCentered },
      { id: 'full-width', label: 'Full Width', thumbnail: SVG_THUMBNAILS.videoFullWidth },
    ],
  },
];

/**
 * Get available layout variants for a given block type.
 * Returns layout IDs as a string array for backwards compatibility.
 */
export function getLayoutsForType(type: string): string[] {
  const def = BLOCK_TYPE_DEFINITIONS.find(bt => bt.type === type);
  return def?.layouts.map(l => l.id) || [];
}

/**
 * Get full layout option objects for a given block type.
 */
export function getLayoutOptionsForType(type: string): LayoutOption[] {
  const def = BLOCK_TYPE_DEFINITIONS.find(bt => bt.type === type);
  return def?.layouts || [];
}
