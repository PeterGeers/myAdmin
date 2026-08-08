# Block Item Editors — Tasks

## Context

The BlockConfigurator currently shows "Item editor coming in next phase" for block types that have `items` arrays (FAQ, Testimonials, Pricing). This task implements inline item editors for each.

**Pattern:** Each item editor allows add/edit/remove of items within the block's `properties.items` array. Changes flow through `onUpdate` to the parent (auto-save).

## Phase 1: FAQ Item Editor

- [x] 1.1 Create `FaqItemEditor.tsx` component
  - Add item button (+ Vraag toevoegen)
  - List of existing items with question preview
  - Click item → expand inline edit (question + answer fields)
  - Remove item button (with confirmation)
  - Reorder items (move up/down)
- [x] 1.2 Wire into `BlockConfigurator.tsx` — render FaqItemEditor when `section.type === 'faq'`
- [x] 1.3 Add translation keys for FAQ editor labels (EN + NL)
- [ ] 1.4 Test: add 3 FAQ items, reorder, remove one, publish, verify on CloudFront page
- [x] 1.5 Verify standalone HTML renders FAQ items as `<details>` accordion

## Phase 2: Testimonials Item Editor

- [x] 2.1 Create `TestimonialsItemEditor.tsx` component
  - Add item button (+ Testimonial toevoegen)
  - Fields per item: quote (textarea), author (text), role/company (text, optional)
  - Inline expand/collapse per item
  - Remove + reorder
- [x] 2.2 Wire into `BlockConfigurator.tsx` for `section.type === 'testimonials'`
- [x] 2.3 Add translation keys (EN + NL)
- [ ] 2.4 Test: add testimonials, publish, verify on CloudFront

## Phase 3: Pricing Item Editor

- [x] 3.1 Create `PricingItemEditor.tsx` component
  - Add item button (+ Pakket toevoegen)
  - Fields per item: name (text), price (text), description (textarea), features (optional list)
  - Inline expand/collapse
  - Remove + reorder
- [x] 3.2 Wire into `BlockConfigurator.tsx` for `section.type === 'pricing'`
- [x] 3.3 Add translation keys (EN + NL)
- [ ] 3.4 Test: add pricing cards, publish, verify on CloudFront

## Phase 4: Gallery Item Editor

- [x] 4.1 Create `GalleryItemEditor.tsx` component
  - Add image button (uses existing ImageUploader)
  - Grid preview of uploaded images
  - Remove image
  - Reorder images (drag or up/down)
  - Optional alt text per image
- [x] 4.2 Wire into `BlockConfigurator.tsx` for `section.type === 'gallery'`
- [x] 4.3 Test: upload images, reorder, publish, verify on CloudFront

## Shared Components

- [x] 5.1 Extract `ItemListEditor` — reusable wrapper for add/remove/reorder pattern
  - Props: items array, renderItem function, onAdd, onRemove, onReorder
  - Provides move up/down buttons, remove with confirmation, add button
- [x] 5.2 Use `ItemListEditor` in all 4 editors above (refactor after Phase 1)

## Design Notes

- All editors render inside the existing `BlockConfigurator` panel (380px wide)
- Dark theme: `bg="gray.700"`, `color="white"`, same as existing fields
- Items collapsed by default, expand on click to edit
- Changes trigger parent `onUpdate` → auto-save
- No separate save button needed (same auto-save as block properties)
- Translation keys follow pattern: `landingPage.itemEditor.{blockType}.{key}`

## Dependencies

- Existing: `BlockConfigurator.tsx`, `LandingPageEditor.tsx` (auto-save), `ImageUploader.tsx`
- No new packages needed
- No backend changes needed (items are stored in DynamoDB as part of the sections array)
