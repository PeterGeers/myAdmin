# Translation Usage Guide

Quick reference for using translations in myAdmin components.

## Setup

The i18n infrastructure is already configured. Just import and use the `useTranslation` hook.

## Basic Usage

### 1. Import the hook

```typescript
import { useTranslation } from "react-i18next";
```

### 2. Use in component

```typescript
const MyComponent: React.FC = () => {
  const { t } = useTranslation();

  return (
    <Button>{t('common:buttons.save')}</Button>
  );
};
```

## Translation Key Format

Keys use namespace:category.key format:

```
namespace:category.key
```

Examples:

- `common:buttons.save` → "Save" / "Opslaan"
- `common:status.loading` → "Loading..." / "Laden..."
- `common:messages.success` → "Successfully saved" / "Succesvol opgeslagen"

## Available Namespaces

- `common` - Common UI elements (buttons, labels, messages)
- `auth` - Authentication pages
- `reports` - Reports module
- `str` - Short-term rental module
- `banking` - Banking module
- `admin` - Admin pages
- `errors` - Error messages
- `validation` - Form validation messages

## Common Translations Reference

### Buttons (`common:buttons.*`)

```typescript
t("common:buttons.save"); // Save / Opslaan
t("common:buttons.cancel"); // Cancel / Annuleren
t("common:buttons.delete"); // Delete / Verwijderen
t("common:buttons.edit"); // Edit / Bewerken
t("common:buttons.close"); // Close / Sluiten
t("common:buttons.submit"); // Submit / Verzenden
t("common:buttons.confirm"); // Confirm / Bevestigen
t("common:buttons.back"); // Back / Terug
t("common:buttons.next"); // Next / Volgende
t("common:buttons.add"); // Add / Toevoegen
t("common:buttons.remove"); // Remove / Verwijderen
t("common:buttons.create"); // Create / Aanmaken
t("common:buttons.update"); // Update / Bijwerken
t("common:buttons.search"); // Search / Zoeken
t("common:buttons.filter"); // Filter / Filteren
t("common:buttons.export"); // Export / Exporteren
t("common:buttons.import"); // Import / Importeren
t("common:buttons.download"); // Download / Downloaden
t("common:buttons.upload"); // Upload / Uploaden
t("common:buttons.print"); // Print / Afdrukken
t("common:buttons.refresh"); // Refresh / Vernieuwen
t("common:buttons.reset"); // Reset / Resetten
t("common:buttons.clear"); // Clear / Wissen
t("common:buttons.apply"); // Apply / Toepassen
t("common:buttons.ok"); // OK / OK
t("common:buttons.yes"); // Yes / Ja
t("common:buttons.no"); // No / Nee
t("common:buttons.continue"); // Continue / Doorgaan
t("common:buttons.tryAgain"); // Try Again / Opnieuw proberen
t("common:buttons.retry"); // Retry / Opnieuw
t("common:buttons.approve"); // Approve / Goedkeuren
t("common:buttons.process"); // Process / Verwerken
t("common:buttons.generate"); // Generate / Genereren
t("common:buttons.calculate"); // Calculate / Berekenen
t("common:buttons.check"); // Check / Controleren
t("common:buttons.validate"); // Validate / Valideren
t("common:buttons.review"); // Review / Beoordelen
t("common:buttons.preview"); // Preview / Voorbeeld
t("common:buttons.new"); // New / Nieuw
```

### Status Messages (`common:status.*`)

```typescript
t("common:status.loading"); // Loading... / Laden...
t("common:status.processing"); // Processing... / Verwerken...
t("common:status.saving"); // Saving... / Opslaan...
t("common:status.uploading"); // Uploading... / Uploaden...
t("common:status.downloading"); // Downloading... / Downloaden...
t("common:status.checking"); // Checking... / Controleren...
t("common:status.validating"); // Validating... / Valideren...
t("common:status.calculating"); // Calculating... / Berekenen...
t("common:status.generating"); // Generating... / Genereren...
t("common:status.success"); // Success / Succesvol
t("common:status.error"); // Error / Fout
t("common:status.warning"); // Warning / Waarschuwing
t("common:status.info"); // Information / Informatie
t("common:status.complete"); // Complete / Voltooid
t("common:status.pending"); // Pending / In behandeling
t("common:status.failed"); // Failed / Mislukt
```

### Messages (`common:messages.*`)

```typescript
t("common:messages.success"); // Successfully saved / Succesvol opgeslagen
t("common:messages.error"); // An error occurred / Er is een fout opgetreden
t("common:messages.errorOccurred"); // An error occurred / Er is een fout opgetreden
t("common:messages.noData"); // No data available / Geen gegevens beschikbaar
t("common:messages.noResults"); // No results found / Geen resultaten gevonden
t("common:messages.confirmDelete"); // Are you sure you want to delete this? / Weet u zeker dat u dit wilt verwijderen?
t("common:messages.confirmAction"); // Are you sure you want to perform this action? / Weet u zeker dat u deze actie wilt uitvoeren?
t("common:messages.unsavedChanges"); // You have unsaved changes / U heeft niet-opgeslagen wijzigingen
t("common:messages.copiedToClipboard"); // Copied to clipboard! / Gekopieerd naar klembord!
t("common:messages.selectFile"); // Select a file / Selecteer een bestand
t("common:messages.selectFolder"); // Select a folder / Selecteer een map
t("common:messages.required"); // Required field / Verplicht veld
t("common:messages.invalidFormat"); // Invalid format / Ongeldig formaat
t("common:messages.tryAgainLater"); // Please try again later / Probeer het later opnieuw
```

### Labels (`common:labels.*`)

```typescript
t("common:labels.date"); // Date / Datum
t("common:labels.description"); // Description / Omschrijving
t("common:labels.amount"); // Amount / Bedrag
t("common:labels.total"); // Total / Totaal
t("common:labels.subtotal"); // Subtotal / Subtotaal
t("common:labels.file"); // File / Bestand
t("common:labels.folder"); // Folder / Map
t("common:labels.name"); // Name / Naam
t("common:labels.type"); // Type / Type
t("common:labels.status"); // Status / Status
t("common:labels.actions"); // Actions / Acties
t("common:labels.details"); // Details / Details
t("common:labels.reference"); // Reference / Referentie
t("common:labels.notes"); // Notes / Notities
t("common:labels.search"); // Search / Zoeken
t("common:labels.filter"); // Filter / Filter
t("common:labels.from"); // From / Van
t("common:labels.to"); // To / Tot
t("common:labels.year"); // Year / Jaar
t("common:labels.month"); // Month / Maand
t("common:labels.quarter"); // Quarter / Kwartaal
t("common:labels.all"); // All / Alle
t("common:labels.selected"); // Selected / Geselecteerd
t("common:labels.none"); // None / Geen
```

### Navigation (`common:navigation.*`)

```typescript
t("common:navigation.home"); // Home / Home
t("common:navigation.dashboard"); // Dashboard / Dashboard
t("common:navigation.back"); // Back / Terug
t("common:navigation.next"); // Next / Volgende
t("common:navigation.previous"); // Previous / Vorige
t("common:navigation.first"); // First / Eerste
t("common:navigation.last"); // Last / Laatste
```

### Time (`common:time.*`)

```typescript
t("common:time.today"); // Today / Vandaag
t("common:time.yesterday"); // Yesterday / Gisteren
t("common:time.tomorrow"); // Tomorrow / Morgen
t("common:time.thisWeek"); // This week / Deze week
t("common:time.thisMonth"); // This month / Deze maand
t("common:time.thisYear"); // This year / Dit jaar
t("common:time.lastWeek"); // Last week / Vorige week
t("common:time.lastMonth"); // Last month / Vorige maand
t("common:time.lastYear"); // Last year / Vorig jaar
```

### Units (`common:units.*`)

```typescript
t("common:units.items"); // items / items
t("common:units.records"); // records / records
t("common:units.transactions"); // transactions / transacties
t("common:units.files"); // files / bestanden
t("common:units.folders"); // folders / mappen
t("common:units.days"); // days / dagen
t("common:units.weeks"); // weeks / weken
t("common:units.months"); // months / maanden
t("common:units.years"); // years / jaren
```

## Real-World Examples

### Example 1: Simple Button

```typescript
<Button onClick={handleSave}>
  {t('common:buttons.save')}
</Button>
```

### Example 2: Loading State

```typescript
<Button
  isLoading={loading}
  loadingText={t('common:status.saving')}
>
  {t('common:buttons.save')}
</Button>
```

### Example 3: Confirmation Dialog

```typescript
const confirmDelete = () => {
  if (window.confirm(t("common:messages.confirmDelete"))) {
    handleDelete();
  }
};
```

### Example 4: Toast Notification

```typescript
toast({
  title: t("common:status.success"),
  description: t("common:messages.success"),
  status: "success",
});
```

### Example 5: Form Label

```typescript
<FormLabel>{t('common:labels.description')}</FormLabel>
<Input placeholder={t('common:labels.description')} />
```

### Example 6: Table Header

```typescript
<Thead>
  <Tr>
    <Th>{t('common:labels.date')}</Th>
    <Th>{t('common:labels.description')}</Th>
    <Th>{t('common:labels.amount')}</Th>
    <Th>{t('common:labels.actions')}</Th>
  </Tr>
</Thead>
```

### Example 7: Status Message

```typescript
{loading && <Text>{t('common:status.loading')}</Text>}
{error && <Text color="red.500">{t('common:messages.error')}</Text>}
{success && <Text color="green.500">{t('common:messages.success')}</Text>}
```

### Example 8: Modal Buttons

```typescript
<ModalFooter>
  <Button onClick={onClose}>
    {t('common:buttons.cancel')}
  </Button>
  <Button colorScheme="blue" onClick={handleSubmit}>
    {t('common:buttons.confirm')}
  </Button>
</ModalFooter>
```

## Working Example

See `frontend/src/components/DuplicateWarningDialog.tsx` for a complete working example.

## Best Practices

1. **Always use translation keys** - Never hardcode UI text
2. **Use appropriate namespace** - `common:` for general UI, module-specific for specialized text
3. **Keep keys organized** - Use the category structure (buttons, labels, messages, etc.)
4. **Test both languages** - Switch language in UI to verify translations work
5. **Add new keys to both files** - Always update both `nl` and `en` JSON files

## Adding New Translations

1. Add key to `frontend/src/locales/nl/common.json`
2. Add same key to `frontend/src/locales/en/common.json`
3. Use in component: `t('common:category.key')`
4. Test in both languages

## Language Switching

Users can switch language using the language selector in the header (🇳🇱/🇬🇧 dropdown).

The selected language is:

- Stored in localStorage
- Saved to user's Cognito profile
- Applied immediately without page refresh

## Current Status

- ✅ Infrastructure complete
- ✅ Common translations complete (100+ strings)
- 🔄 Component updates in progress
- ⏳ Module-specific translations pending

## Next Steps

Continue updating components to use translation keys. Priority order:

1. Common components (buttons, modals, forms)
2. Navigation and layout
3. Auth module
4. Reports module
5. STR module
6. Banking module
7. Admin module
