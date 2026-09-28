/**
 * LazySelect
 *
 * A single-value, ALWAYS-searchable dropdown (combobox) for forms and modals. At rest it renders the
 * CURRENT value as a closed, read-looking control; the option list is revealed only on interaction
 * and can be narrowed by typing. Options come from an eager array OR a (possibly async) function —
 * the component is agnostic to whether the data is an enum, an API feed, a SQL query, or an external
 * service (see `useLazyOptions`).
 *
 * Core guarantee — "tolerate legacy, enforce on change": the stored value is ALWAYS displayed at
 * rest and is NEVER blanked or silently coerced. An out-of-set value shows via `renderMissingValue`
 * (raw value by default) and is preserved until the user deliberately picks another option.
 *
 * The listbox is SELF-OWNED (plain Chakra `Box`es, not a Chakra `Menu`) so open/close/keyboard paths
 * remain exercisable under the auto-mocked Chakra in tests (steering 33).
 *
 * @module components/common/LazySelect
 * @see .kiro/specs/Common/Frameworks/lazy-select/design.md
 * _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.4, 4.2, 4.3, 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3_
 */

import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Box, Input, Spinner, Text } from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { useLazyOptions } from '../../hooks/useLazyOptions';
import { resolveOptionLabel } from './lazySelect.types';
import type { LazyOption, LazySelectProps } from './lazySelect.types';

/** Size tokens for the trigger/options, mapped from the Chakra `size` variant (R7.2). */
const SIZE_STYLES: Record<
  NonNullable<LazySelectProps['size']>,
  { minH: string; fontSize: string; px: number; py: number }
> = {
  sm: { minH: '32px', fontSize: 'sm', px: 2, py: 1 },
  md: { minH: '40px', fontSize: 'md', px: 3, py: 2 },
  lg: { minH: '48px', fontSize: 'lg', px: 4, py: 3 },
};

function LazySelectInner<V extends string = string>(props: LazySelectProps<V>): React.ReactElement {
  const {
    value,
    onChange,
    options,
    optionsDepKey,
    label,
    placeholder,
    filterOption,
    getOptionLabel,
    renderMissingValue,
    isDisabled = false,
    isReadOnly = false,
    isInvalid = false,
    size = 'md',
    bg = 'gray.700',
    color = 'white',
    borderColor = 'gray.600',
    width,
    name,
  } = props;

  const { t, i18n } = useTypedTranslation('common');
  const lang = i18n?.language;

  const { options: loadedOptions, isLoading, error, ensureLoaded } = useLazyOptions<V>(
    options,
    optionsDepKey,
  );

  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [activeIndex, setActiveIndex] = useState(-1);

  const triggerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const reactId = useId();
  const baseId = name ? `lazyselect-${name}` : `lazyselect-${reactId}`;
  const listboxId = `${baseId}-listbox`;
  const optionId = (index: number) => `${baseId}-option-${index}`;

  const nonInteractive = isDisabled || isReadOnly;

  // Resolve an option's display label (caller resolver > localized map > raw value) (R1.2).
  const labelOf = useCallback(
    (opt: LazyOption<V>) => resolveOptionLabel(opt, getOptionLabel, lang),
    [getOptionLabel, lang],
  );

  // The option (if any) whose value equals the current value — used for the in-set rest label and
  // for `aria-selected` in the open list.
  const selectedOption = useMemo(
    () => (value === '' ? undefined : loadedOptions.find((o) => o.value === value)),
    [loadedOptions, value],
  );

  /**
   * Rest-state display (R1):
   *  - empty value → placeholder (R1.4)
   *  - value in the option set → its resolved label (R1.2)
   *  - value NOT in the set (or options not yet loaded) → `renderMissingValue` / raw value (R1.3)
   */
  const displayNode: React.ReactNode = useMemo(() => {
    if (value === '') {
      return (
        <Text as="span" color="gray.400" fontSize={SIZE_STYLES[size].fontSize} noOfLines={1}>
          {placeholder ?? ''}
        </Text>
      );
    }
    if (selectedOption) {
      return (
        <Text as="span" color={color} fontSize={SIZE_STYLES[size].fontSize} noOfLines={1}>
          {labelOf(selectedOption)}
        </Text>
      );
    }
    // Out-of-set (legacy / role-gated / not-yet-loaded): show the raw value, never the placeholder.
    return (
      <Text as="span" color={color} fontSize={SIZE_STYLES[size].fontSize} noOfLines={1}>
        {renderMissingValue ? renderMissingValue(value as V) : (value as string)}
      </Text>
    );
  }, [value, selectedOption, placeholder, renderMissingValue, labelOf, color, size]);

  /**
   * Options offered in the open list (R5): only those satisfying the caller `filterOption`, then
   * narrowed by the typed search (case-insensitive substring on the display label, R2.3). The
   * out-of-set current value is NEVER injected here (R5.2 / Filter Soundness).
   */
  const visibleOptions = useMemo(() => {
    const permitted = filterOption ? loadedOptions.filter(filterOption) : loadedOptions;
    const q = search.trim().toLowerCase();
    if (!q) return permitted;
    return permitted.filter((o) => labelOf(o).toLowerCase().includes(q));
  }, [loadedOptions, filterOption, search, labelOf]);

  const close = useCallback((restoreFocus: boolean) => {
    setIsOpen(false);
    setSearch('');
    setActiveIndex(-1);
    if (restoreFocus) {
      // Escape restores focus to the trigger (R2.4 / R6.3).
      triggerRef.current?.focus();
    }
  }, []);

  const open = useCallback(() => {
    if (nonInteractive) return; // disabled/read-only never opens (R2.5).
    setIsOpen(true);
    ensureLoaded(); // resolve a function source on first open (R2.2 / R4.2).
  }, [nonInteractive, ensureLoaded]);

  // Move keyboard focus into the search input when the list opens.
  useEffect(() => {
    if (isOpen) {
      // Defer so the input is mounted before we focus it.
      const id = window.setTimeout(() => searchRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [isOpen]);

  // Keep the active option in range as the visible list changes (typing/filtering).
  useEffect(() => {
    if (!isOpen) return;
    setActiveIndex((prev) => {
      if (visibleOptions.length === 0) return -1;
      if (prev < 0) return -1; // no active option until the user arrows in
      return Math.min(prev, visibleOptions.length - 1);
    });
  }, [isOpen, visibleOptions.length]);

  // Outside click / focus loss closes without changing the value (R2.4).
  useEffect(() => {
    if (!isOpen) return undefined;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        close(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [isOpen, close]);

  const selectOption = useCallback(
    (opt: LazyOption<V>) => {
      if (opt.disabled) return;
      onChange(opt.value); // emit exactly the picked value; never coerce (R3.1 / R3.4).
      close(false);
    },
    [onChange, close],
  );

  // Keyboard handling on the trigger (closed) — open affordances (R2.2).
  const onTriggerKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (nonInteractive) return;
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar' || e.key === 'ArrowDown') {
        e.preventDefault();
        open();
      }
    },
    [nonInteractive, open],
  );

  // Keyboard handling while open (search input has focus) (R6.3).
  const onSearchKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setActiveIndex((prev) =>
            visibleOptions.length === 0 ? -1 : Math.min(prev + 1, visibleOptions.length - 1),
          );
          break;
        case 'ArrowUp':
          e.preventDefault();
          setActiveIndex((prev) => (prev <= 0 ? 0 : prev - 1));
          break;
        case 'Home':
          e.preventDefault();
          if (visibleOptions.length > 0) setActiveIndex(0);
          break;
        case 'End':
          e.preventDefault();
          if (visibleOptions.length > 0) setActiveIndex(visibleOptions.length - 1);
          break;
        case 'Enter': {
          e.preventDefault();
          const opt = activeIndex >= 0 ? visibleOptions[activeIndex] : undefined;
          if (opt) selectOption(opt);
          break;
        }
        case 'Escape':
          e.preventDefault();
          close(true); // close without change + restore focus (R2.4).
          break;
        default:
          break;
      }
    },
    [visibleOptions, activeIndex, selectOption, close],
  );

  const sizeStyle = SIZE_STYLES[size];
  const activeDescendant = activeIndex >= 0 ? optionId(activeIndex) : undefined;

  // Non-interactive (disabled/read-only): plain text, no open affordance, no combobox role (R1.5/R2.5).
  if (nonInteractive) {
    return (
      <Box
        ref={rootRef}
        width={width}
        data-testid={name ? `${name}-lazyselect` : undefined}
        aria-label={label}
      >
        <Box
          minH={sizeStyle.minH}
          px={sizeStyle.px}
          py={sizeStyle.py}
          display="flex"
          alignItems="center"
          color={color}
          opacity={isDisabled ? 0.6 : 1}
          aria-disabled={isDisabled || undefined}
          aria-readonly={isReadOnly || undefined}
        >
          {displayNode}
        </Box>
      </Box>
    );
  }

  return (
    <Box ref={rootRef} position="relative" width={width} data-testid={name ? `${name}-lazyselect` : undefined}>
      {/* Trigger — ARIA combobox (R6.1). */}
      <Box
        ref={triggerRef}
        role="combobox"
        tabIndex={0}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-label={label}
        aria-invalid={isInvalid || undefined}
        onClick={open}
        onKeyDown={onTriggerKeyDown}
        minH={sizeStyle.minH}
        px={sizeStyle.px}
        py={sizeStyle.py}
        display="flex"
        alignItems="center"
        justifyContent="space-between"
        cursor="pointer"
        bg={bg}
        color={color}
        borderWidth="1px"
        borderColor={isInvalid ? 'red.400' : borderColor}
        borderRadius="md"
        _hover={{ borderColor: isInvalid ? 'red.400' : 'gray.500' }}
        _focus={{ outline: 'none', boxShadow: 'outline' }}
      >
        {displayNode}
        <Box as="span" aria-hidden="true" ml={2} color="gray.400" fontSize="xs">
          ▾
        </Box>
      </Box>

      {isOpen && (
        <Box
          position="absolute"
          zIndex={1000}
          mt={1}
          left={0}
          right={0}
          bg={bg}
          borderWidth="1px"
          borderColor={borderColor}
          borderRadius="md"
          boxShadow="lg"
          overflow="hidden"
        >
          {/* Search box (R2.3). */}
          <Box p={1} borderBottomWidth="1px" borderColor={borderColor}>
            <Input
              ref={searchRef}
              size={size}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={onSearchKeyDown}
              placeholder={t('placeholders.typeToSearch')}
              aria-label={t('placeholders.typeToSearch')}
              aria-controls={listboxId}
              aria-activedescendant={activeDescendant}
              autoComplete="off"
              bg={bg}
              color={color}
              borderColor={borderColor}
            />
          </Box>

          {/* Listbox — self-owned (R6.2 / test-mock safe). */}
          <Box
            id={listboxId}
            role="listbox"
            aria-label={label}
            maxH="240px"
            overflowY="auto"
          >
            {isLoading && (
              <Box display="flex" alignItems="center" px={3} py={2} color="gray.300" fontSize={sizeStyle.fontSize}>
                <Spinner size="sm" mr={2} />
                <Text as="span">{t('status.loading')}</Text>
              </Box>
            )}

            {!isLoading && error && (
              <Box px={3} py={2} color="red.300" fontSize={sizeStyle.fontSize} role="alert">
                {t('messages.error')}
              </Box>
            )}

            {!isLoading && !error && visibleOptions.length === 0 && (
              <Box px={3} py={2} color="gray.400" fontSize={sizeStyle.fontSize}>
                {t('placeholders.noOptions')}
              </Box>
            )}

            {!isLoading &&
              !error &&
              visibleOptions.map((opt, index) => {
                const isActive = index === activeIndex;
                const isSelected = value !== '' && opt.value === value;
                return (
                  <Box
                    key={opt.value}
                    id={optionId(index)}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={opt.disabled || undefined}
                    // Use mousedown so selection fires before the trigger's blur/outside-click closes.
                    onMouseDown={(e) => {
                      e.preventDefault();
                      selectOption(opt);
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                    px={3}
                    py={2}
                    cursor={opt.disabled ? 'not-allowed' : 'pointer'}
                    opacity={opt.disabled ? 0.5 : 1}
                    bg={isActive ? 'gray.600' : isSelected ? 'gray.650' : 'transparent'}
                    color={color}
                    fontSize={sizeStyle.fontSize}
                    _hover={{ bg: opt.disabled ? 'transparent' : 'gray.600' }}
                  >
                    {labelOf(opt)}
                  </Box>
                );
              })}
          </Box>
        </Box>
      )}
    </Box>
  );
}

// Generic-friendly memo wrapper (React.memo drops the generic, so cast it back).
const LazySelect = React.memo(LazySelectInner) as typeof LazySelectInner;

export default LazySelect;
export { LazySelect };
