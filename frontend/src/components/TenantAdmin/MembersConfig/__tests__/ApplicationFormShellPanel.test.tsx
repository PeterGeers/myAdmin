/**
 * Tests for the Application form-shell panel + its pure helpers (spec 11, task 3.2; R5.1/R5.2/R5.3,
 * design §2.3/§3.1/§6).
 *
 * The change-with-tests pairing for the new `ApplicationFormShellPanel` + `applicationShellForm`
 * behavior (the full dedicated suite is task 3.5). It asserts the R5 contract this task owns:
 *  - the public URL is DERIVED from the slug and DISPLAYED; absent slug → "no address yet" + a
 *    link to the Landing Page editor (R5.1 / E4);
 *  - the embed-mode chooser (standalone/iframe); iframe surfaces a copy-ready `<iframe>` snippet
 *    referencing the public URL + an allowed-origin input authoring the origins list (R5.2);
 *  - the consent-notice version BUMPS when the text changes and is KEPT when it does not (R5.3);
 *  - the `config#mail` working body is SEEDED from the loaded mail_config and carries the Mail
 *    sub-tab scalars through verbatim (R5.5 — never clobbers them); standalone omits origins.
 *
 * The component takes `lang` directly (no i18n), so a plain Chakra render suffices.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '../../../../test-utils';
import type { FieldConfig } from '../../../../types/members';
import { ApplicationFormShellPanel } from '../ApplicationFormShellPanel';
import {
  CONFIRMED_EMBED_ORIGINS,
  IFRAME_EMBED_ELEMENT_ID,
  type ShellFormValues,
  buildIframeResizeListenerScript,
  buildIframeSnippet,
  deriveApplicationFormUrl,
  deriveFrameOrigin,
  derivePublicUrl,
  mailConfigToShellValues,
  parseEmbedOrigins,
  resolveConsentVersion,
  toShellMailBody,
} from '../applicationShellForm';
import {
  IFRAME_RESIZE_MESSAGE_TYPE,
  IFRAME_RESIZE_SOURCE,
} from '../../../public/application/iframeResize';

/* ------------------------------------------------------------------ */
/*  Pure helpers (applicationShellForm)                                */
/* ------------------------------------------------------------------ */
describe('applicationShellForm — public URL derivation (R5.1 / E4)', () => {
  it('derives <slug>.jabaki.nl from a slug', () => {
    expect(derivePublicUrl('h-dcn')).toBe('https://h-dcn.jabaki.nl');
  });
  it('returns null when there is no slug (no address yet)', () => {
    expect(derivePublicUrl(null)).toBeNull();
    expect(derivePublicUrl('')).toBeNull();
    expect(derivePublicUrl('   ')).toBeNull();
  });
});

describe('applicationShellForm — application-form URL (/apply) derivation (R5.1 / E4)', () => {
  it('derives <slug>.jabaki.nl/apply — the form lives at /apply, landing owns /', () => {
    expect(deriveApplicationFormUrl('h-dcn')).toBe('https://h-dcn.jabaki.nl/apply');
  });
  it('returns null when there is no slug (no address yet)', () => {
    expect(deriveApplicationFormUrl(null)).toBeNull();
    expect(deriveApplicationFormUrl('')).toBeNull();
    expect(deriveApplicationFormUrl('   ')).toBeNull();
  });
});

describe('applicationShellForm — iframe snippet + origins (R5.2)', () => {
  it('builds a snippet referencing the public URL', () => {
    const snippet = buildIframeSnippet('https://h-dcn.jabaki.nl');
    expect(snippet).toContain('src="https://h-dcn.jabaki.nl"');
    expect(snippet).toContain('<iframe');
  });
  it('returns an empty snippet when there is no public URL', () => {
    expect(buildIframeSnippet(null)).toBe('');
  });
  it('tags the iframe with the stable element id (so the resize listener can find it)', () => {
    const snippet = buildIframeSnippet('https://h-dcn.jabaki.nl/apply');
    expect(snippet).toContain(`id="${IFRAME_EMBED_ELEMENT_ID}"`);
  });
  it('parses origins (newline/comma), trims, de-dups, preserves order', () => {
    expect(parseEmbedOrigins('https://a.org\nhttps://b.org, https://a.org\n\n')).toEqual([
      'https://a.org',
      'https://b.org',
    ]);
  });
});

describe('applicationShellForm — responsive iframe-resize snippet (E4b / task 5.4)', () => {
  it('derives the frame ORIGIN (scheme+host) from the public URL, dropping the path', () => {
    expect(deriveFrameOrigin('https://h-dcn.jabaki.nl/apply')).toBe('https://h-dcn.jabaki.nl');
    expect(deriveFrameOrigin(null)).toBeNull();
    expect(deriveFrameOrigin('not a url')).toBeNull();
  });

  it('the snippet carries a resize listener scoped to the hosted form ORIGIN (not a wildcard)', () => {
    const snippet = buildIframeSnippet('https://h-dcn.jabaki.nl/apply');
    expect(snippet).toContain('<script>');
    expect(snippet).toContain('addEventListener("message"');
    // Origin-pinned to the exact hosted-form origin — never a wildcard.
    expect(snippet).toContain('"https://h-dcn.jabaki.nl"');
    expect(snippet).toContain('event.origin !== ORIGIN');
    expect(snippet).not.toContain('"*"');
  });

  it('the listener validates the message TYPE + SOURCE tokens (in lockstep with the emitter)', () => {
    const script = buildIframeResizeListenerScript('https://h-dcn.jabaki.nl');
    expect(script).toContain(JSON.stringify(IFRAME_RESIZE_MESSAGE_TYPE));
    expect(script).toContain(JSON.stringify(IFRAME_RESIZE_SOURCE));
    // It resizes ONLY the specific iframe, nothing else on the host page.
    expect(script).toContain(JSON.stringify(IFRAME_EMBED_ELEMENT_ID));
    expect(script).toContain('style.height');
  });

  it('omits the listener script when the origin cannot be derived (no-JS fixed-height fallback)', () => {
    expect(buildIframeResizeListenerScript(null)).toBe('');
  });

  /**
   * A behavioral check: run the GENERATED listener against the embedder's window and assert it only
   * resizes the iframe for a well-formed, same-origin height message — and ignores a wrong-origin
   * one, a wrong-shape one, and a non-numeric height (secure postMessage, CWE-346).
   */
  it('the generated listener resizes ONLY on a valid, origin-matching height message', () => {
    const FRAME_ORIGIN = 'https://h-dcn.jabaki.nl';
    // Strip the wrapping <script>…</script> so we can execute the listener body directly.
    // Case-insensitive + attribute-tolerant so it matches <SCRIPT ...> too (js/bad-tag-filter).
    const script = buildIframeResizeListenerScript(FRAME_ORIGIN).replace(
      /<\/?script\b[^>]*>/gi,
      '',
    );

    // A fake iframe element the listener targets by id.
    const frame = { style: { height: '' } };
    const getElementById = vi.fn((id: string) =>
      id === IFRAME_EMBED_ELEMENT_ID ? (frame as unknown as HTMLElement) : null,
    );
    let handler: ((event: { origin: string; data: unknown }) => void) | null = null;
    const fakeWindow = {
      addEventListener: (type: string, fn: (event: { origin: string; data: unknown }) => void) => {
        if (type === 'message') handler = fn;
      },
    };
    // Execute the generated script with our fakes bound as window/document.
    // eslint-disable-next-line no-new-func
    new Function('window', 'document', script)(fakeWindow, { getElementById });
    expect(handler).toBeTypeOf('function');

    const valid = {
      type: IFRAME_RESIZE_MESSAGE_TYPE,
      source: IFRAME_RESIZE_SOURCE,
      height: 742.3,
    };

    // Wrong origin → ignored.
    handler!({ origin: 'https://evil.example.org', data: valid });
    expect(frame.style.height).toBe('');

    // Wrong shape → ignored.
    handler!({ origin: FRAME_ORIGIN, data: { type: 'something-else', height: 500 } });
    expect(frame.style.height).toBe('');

    // Non-numeric height → ignored.
    handler!({ origin: FRAME_ORIGIN, data: { ...valid, height: 'tall' } });
    expect(frame.style.height).toBe('');

    // Valid + same origin → resizes (ceil'd).
    handler!({ origin: FRAME_ORIGIN, data: valid });
    expect(frame.style.height).toBe('743px');
  });
});

describe('applicationShellForm — confirmed-target seeding (R5.2b)', () => {
  it('exposes the two confirmed v1 external targets', () => {
    expect(CONFIRMED_EMBED_ORIGINS).toEqual(['https://sites.google.com', 'https://portal.h-dcn.nl']);
  });

  it('SEEDS the confirmed targets when the tenant has authored no origins (standalone stays default)', () => {
    const values = mailConfigToShellValues({ fields: [] }, 'h-dcn');
    expect(values.embedMode).toBe('standalone');
    expect(values.embedOrigins).toEqual(['https://sites.google.com', 'https://portal.h-dcn.nl']);
  });

  it('seeds the confirmed targets even when there is no mail_config at all', () => {
    const values = mailConfigToShellValues(null, 'h-dcn');
    expect(values.embedOrigins).toEqual(['https://sites.google.com', 'https://portal.h-dcn.nl']);
  });

  it('a tenant with stored origins keeps THEIR list verbatim (seed never overrides)', () => {
    const cfg: FieldConfig = {
      fields: [],
      mail_config: {
        mail_enabled: true,
        mail_certified: true,
        application_embed_origins: ['https://own.example.org'],
      },
    };
    const values = mailConfigToShellValues(cfg, 'h-dcn');
    expect(values.embedMode).toBe('iframe');
    expect(values.embedOrigins).toEqual(['https://own.example.org']);
  });

  it('a seeded-but-standalone tenant still writes NO origins (back-compatible)', () => {
    // The seed is a starting point only — while standalone, toShellMailBody omits the key.
    const values = mailConfigToShellValues({ fields: [] }, 'h-dcn');
    const body = toShellMailBody(values, { mail_enabled: false, mail_certified: false }, '');
    expect(body.application_embed_origins).toBeUndefined();
  });
});

describe('applicationShellForm — consent version bump (R5.3)', () => {
  const base: ShellFormValues = {
    slug: 'x',
    embedMode: 'standalone',
    embedOrigins: [],
    consentVersion: 'v1',
    consentTextNl: 'oude tekst',
    consentTextEn: 'old text',
  };

  it('keeps the version when the text is unchanged', () => {
    expect(resolveConsentVersion(base, base)).toBe('v1');
  });

  it('bumps to a NEW version when the text changes', () => {
    const changed = { ...base, consentTextEn: 'new text' };
    const next = resolveConsentVersion(changed, base, new Date('2026-10-21T10:11:12Z'));
    expect(next).not.toBe('v1');
    expect(next).toBe('v20261021-101112');
  });

  it('assigns a first version for a brand-new notice with no version yet', () => {
    const fresh: ShellFormValues = { ...base, consentVersion: '', consentTextNl: 'nieuw', consentTextEn: '' };
    const emptyBaseline: ShellFormValues = { ...fresh, consentTextNl: '', consentTextEn: '' };
    const next = resolveConsentVersion(fresh, emptyBaseline, new Date('2026-10-21T10:11:12Z'));
    expect(next).toBe('v20261021-101112');
  });
});

describe('applicationShellForm — config#mail body assembly (R5.5)', () => {
  const loaded: FieldConfig['mail_config'] = {
    mail_enabled: true,
    mail_certified: true,
    mail_domain: 'h-dcn.nl',
    mail_local_part: 'noreply',
    mail_reply_to_default: 'board@h-dcn.nl',
    application_scope_copy: true,
  };

  it('carries the Mail sub-tab scalars through VERBATIM (never clobbers them)', () => {
    const values: ShellFormValues = {
      slug: 'h-dcn',
      embedMode: 'standalone',
      embedOrigins: [],
      consentVersion: '',
      consentTextNl: '',
      consentTextEn: '',
    };
    const body = toShellMailBody(values, loaded, '');
    expect(body.mail_enabled).toBe(true);
    expect(body.mail_certified).toBe(true);
    expect(body.mail_domain).toBe('h-dcn.nl');
    expect(body.mail_reply_to_default).toBe('board@h-dcn.nl');
    expect(body.application_scope_copy).toBe(true);
  });

  it('includes a well-formed consent notice and the embed origins when authoring them', () => {
    const values: ShellFormValues = {
      slug: 'h-dcn',
      embedMode: 'iframe',
      embedOrigins: ['https://a.org'],
      consentVersion: 'v9',
      consentTextNl: 'ja',
      consentTextEn: '',
    };
    const body = toShellMailBody(values, loaded, 'v9');
    expect(body.consent_notice).toEqual({ version: 'v9', text: { nl: 'ja' } });
    expect(body.application_embed_origins).toEqual(['https://a.org']);
  });

  it('OMITS the embed origins when standalone, and omits a half-authored consent notice', () => {
    const values: ShellFormValues = {
      slug: 'h-dcn',
      embedMode: 'standalone',
      embedOrigins: ['https://a.org'], // present but standalone → not emitted
      consentVersion: '', // no version → notice omitted even with text
      consentTextNl: 'ja',
      consentTextEn: '',
    };
    const body = toShellMailBody(values, loaded, '');
    expect(body.application_embed_origins).toBeUndefined();
    expect(body.consent_notice).toBeUndefined();
  });

  it('seeds the shell values from a loaded mail_config (iframe mode derived from origins)', () => {
    const cfg: FieldConfig = {
      fields: [],
      mail_config: {
        ...loaded,
        consent_notice: { version: 'v3', text: { nl: 'nl tekst', en: 'en text' } },
        application_embed_origins: ['https://a.org', 'https://b.org'],
      },
    };
    const values = mailConfigToShellValues(cfg, 'h-dcn');
    expect(values.slug).toBe('h-dcn');
    expect(values.embedMode).toBe('iframe');
    expect(values.embedOrigins).toEqual(['https://a.org', 'https://b.org']);
    expect(values.consentVersion).toBe('v3');
    expect(values.consentTextNl).toBe('nl tekst');
    expect(values.consentTextEn).toBe('en text');
  });
});

/* ------------------------------------------------------------------ */
/*  Component (ApplicationFormShellPanel)                              */
/* ------------------------------------------------------------------ */
const BASE_VALUES: ShellFormValues = {
  slug: 'h-dcn',
  embedMode: 'standalone',
  embedOrigins: [],
  consentVersion: 'v1',
  consentTextNl: 'ja',
  consentTextEn: 'yes',
};

function renderPanel(values: ShellFormValues = BASE_VALUES, onChange = vi.fn()) {
  const utils = render(
    <ApplicationFormShellPanel values={values} onChange={onChange} lang="en" />,
  );
  return { ...utils, onChange };
}

describe('ApplicationFormShellPanel — public URL display (R5.1)', () => {
  it('displays the derived public URL when a slug exists', () => {
    renderPanel();
    expect(screen.getByTestId('application-form-shell-public-url')).toHaveTextContent(
      'https://h-dcn.jabaki.nl/apply',
    );
  });

  it('surfaces an "open live form" link to the hosted form, opening in a new tab (R5.1 / R7.3)', () => {
    renderPanel();
    const link = screen.getByTestId('application-form-shell-open-live');
    expect(link).toHaveAttribute('href', 'https://h-dcn.jabaki.nl/apply');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('shows NO "open live form" link when there is no public address yet', () => {
    renderPanel({ ...BASE_VALUES, slug: null });
    expect(screen.queryByTestId('application-form-shell-open-live')).not.toBeInTheDocument();
  });

  it('shows "no address yet" + a Landing Page editor link when no slug', () => {
    renderPanel({ ...BASE_VALUES, slug: null });
    expect(screen.getByTestId('application-form-shell-no-url')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-shell-landing-link')).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-shell-public-url')).not.toBeInTheDocument();
  });
});

describe('ApplicationFormShellPanel — embed mode (R5.2)', () => {
  it('hides the iframe snippet + origins input while standalone', () => {
    renderPanel();
    expect(screen.queryByTestId('application-form-shell-iframe-snippet')).not.toBeInTheDocument();
    expect(screen.queryByTestId('application-form-shell-embed-origins')).not.toBeInTheDocument();
  });

  it('shows a copy-ready snippet referencing the public URL + the origins input when iframe', () => {
    renderPanel({ ...BASE_VALUES, embedMode: 'iframe' });
    expect(screen.getByTestId('application-form-shell-iframe-snippet')).toHaveTextContent(
      'https://h-dcn.jabaki.nl/apply',
    );
    expect(screen.getByTestId('application-form-shell-embed-origins')).toBeInTheDocument();
  });

  it('authoring origins bubbles a parsed list up via onChange', () => {
    const { onChange } = renderPanel({ ...BASE_VALUES, embedMode: 'iframe' });
    fireEvent.change(screen.getByTestId('application-form-shell-embed-origins'), {
      target: { value: 'https://a.org\nhttps://b.org' },
    });
    const next = onChange.mock.calls[0][0] as ShellFormValues;
    expect(next.embedOrigins).toEqual(['https://a.org', 'https://b.org']);
  });

  it('switching to iframe with no origins SEEDS the confirmed targets (R5.2b)', () => {
    const { onChange } = renderPanel({ ...BASE_VALUES, embedMode: 'standalone', embedOrigins: [] });
    fireEvent.click(screen.getByTestId('application-form-shell-embed-iframe'));
    const next = onChange.mock.calls[0][0] as ShellFormValues;
    expect(next.embedMode).toBe('iframe');
    expect(next.embedOrigins).toEqual(['https://sites.google.com', 'https://portal.h-dcn.nl']);
  });

  it('switching to iframe does NOT clobber an existing non-empty origins list', () => {
    const { onChange } = renderPanel({
      ...BASE_VALUES,
      embedMode: 'standalone',
      embedOrigins: ['https://own.example.org'],
    });
    fireEvent.click(screen.getByTestId('application-form-shell-embed-iframe'));
    const next = onChange.mock.calls[0][0] as ShellFormValues;
    expect(next.embedMode).toBe('iframe');
    expect(next.embedOrigins).toEqual(['https://own.example.org']);
  });
});

describe('ApplicationFormShellPanel — consent notice (R5.3)', () => {
  it('displays the current version and edits bubble up via onChange', () => {
    const { onChange } = renderPanel();
    expect(screen.getByTestId('application-form-shell-consent-version')).toHaveTextContent('v1');
    fireEvent.change(screen.getByTestId('application-form-shell-consent-en'), {
      target: { value: 'updated text' },
    });
    const next = onChange.mock.calls[0][0] as ShellFormValues;
    expect(next.consentTextEn).toBe('updated text');
  });
});

describe('ApplicationFormShellPanel — single mail save (R5.5)', () => {
  it('surfaces a save that is disabled until dirty and fires onSaveMail once when clicked', () => {
    const onSaveMail = vi.fn();
    render(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        onSaveMail={onSaveMail}
        mailDirty
        lang="en"
      />,
    );
    const btn = screen.getByTestId('application-form-shell-save-mail');
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect(onSaveMail).toHaveBeenCalledTimes(1);
  });

  it('disables the save when not dirty', () => {
    render(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        onSaveMail={vi.fn()}
        mailDirty={false}
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-shell-save-mail')).toBeDisabled();
  });
});
