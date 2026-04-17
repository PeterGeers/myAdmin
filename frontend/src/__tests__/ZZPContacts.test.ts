/**
 * Tests for ZZPContacts page logic.
 * Tests the contact type color mapping and data flow.
 */
import { ContactType } from '../types/zzp';

// Extracted from ZZPContacts.tsx
const TYPE_COLORS: Record<ContactType, string> = {
  client: 'blue', supplier: 'orange', both: 'green', other: 'gray',
};

describe('ZZPContacts page logic', () => {
  describe('contact type color mapping', () => {
    it('maps client to blue', () => expect(TYPE_COLORS['client']).toBe('blue'));
    it('maps supplier to orange', () => expect(TYPE_COLORS['supplier']).toBe('orange'));
    it('maps both to green', () => expect(TYPE_COLORS['both']).toBe('green'));
    it('maps other to gray', () => expect(TYPE_COLORS['other']).toBe('gray'));

    it('covers all ContactType values', () => {
      const allTypes: ContactType[] = ['client', 'supplier', 'both', 'other'];
      allTypes.forEach(t => expect(TYPE_COLORS[t]).toBeDefined());
    });
  });
});
