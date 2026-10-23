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
  deriveFormSlug,
  deriveFrameOrigin,
  derivePublicUrl,
  mailConfigToShellValues,
  parseEmbedOrigins,
  resolveConsentVersion,
  toShellMailBody,
} from '../applicationShellForm';
import type { ReadinessState } from '../applicationReadiness';
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

describe('applicationShellForm — FORM slug resolution (spec 12 R4 / Phase 1)', () => {
  it('prefers the FORM slug on config#fields over a landing-slug fallback', () => {
    expect(deriveFormSlug({ fields: [], slug: 'hdcn-application-form' }, 'h-dcn')).toBe(
      'hdcn-application-form',
    );
  });
  it('falls back to the landing slug when no form slug is set (older build / unauthored)', () => {
    expect(deriveFormSlug({ fields: [] }, 'h-dcn')).toBe('h-dcn');
    expect(deriveFormSlug({ fields: [], slug: null }, 'h-dcn')).toBe('h-dcn');
    expect(deriveFormSlug({ fields: [], slug: '   ' }, 'h-dcn')).toBe('h-dcn');
  });
  it('returns null when neither a form slug nor a fallback exists (no public address yet)', () => {
    expect(deriveFormSlug({ fields: [] }, null)).toBeNull();
    expect(deriveFormSlug(null, null)).toBeNull();
    expect(deriveFormSlug({ fields: [], slug: '' }, '')).toBeNull();
  });
  it('a NAME ≠ tenant form slug is allowed (slug string independent of tenant)', () => {
    // The form slug need not match the tenant name — deriveFormSlug honours it verbatim.
    expect(deriveFormSlug({ fields: [], slug: 'join-our-club' }, 'h-dcn')).toBe('join-our-club');
  });
  it('mailConfigToShellValues seeds the FORM slug from config#fields (not the landing fallback)', () => {
    const values = mailConfigToShellValues(
      { fields: [], slug: 'hdcn-application-form' },
      'h-dcn',
    );
    expect(values.slug).toBe('hdcn-application-form');
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
    // Execute the listener BODY directly. We do NOT regex-strip the <script> tags (that is a
    // tag-sanitization anti-pattern CodeQL rightly flags — js/incomplete-multi-character-
    // sanitization). Instead we slice between the known, author-controlled delimiters: the
    // helper builds `<script>\n…\n</script>`, so the body is everything between the first
    // `>` and the final `</script>`. No HTML parsing/sanitization involved.
    const wrapped = buildIframeResizeListenerScript(FRAME_ORIGIN);
    const script = wrapped.slice(wrapped.indexOf('>') + 1, wrapped.lastIndexOf('</script>'));

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

  it('rel-hardens the new-tab open-live link (noopener/noreferrer — no window.opener handle)', () => {
    // A target=_blank link MUST carry rel="noopener noreferrer" so the opened tab gets no
    // `window.opener` handle back to the admin app (reverse-tabnabbing, CWE-1022). The checklist's
    // "rel hardened" requirement for the slug link states — pin it so a regression can't drop it.
    renderPanel();
    const rel = screen.getByTestId('application-form-shell-open-live').getAttribute('rel') ?? '';
    expect(rel).toContain('noopener');
    expect(rel).toContain('noreferrer');
  });

  it('shows NO "open live form" link when there is no public address yet', () => {
    renderPanel({ ...BASE_VALUES, slug: null });
    expect(screen.queryByTestId('application-form-shell-open-live')).not.toBeInTheDocument();
  });

  it('shows "no address yet" + a form-slug hint when no slug (spec 12: authored via form config, not the landing editor)', () => {
    // Spec 12 R4/Phase 1: the slug is the FORM slug on config#fields, authored via the SAM
    // config-write — NOT the Landing Page editor. The old landing-editor link is retired; the
    // "no address yet" state now points at the form configuration.
    renderPanel({ ...BASE_VALUES, slug: null });
    expect(screen.getByTestId('application-form-shell-no-url')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-shell-slug-hint')).toBeInTheDocument();
    expect(
      screen.queryByTestId('application-form-shell-landing-link'),
    ).not.toBeInTheDocument();
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

/* ------------------------------------------------------------------ */
/*  Publish button — explicit go-live, readiness-gated, save ≠ publish */
/*  (spec 12 task 6.2 / R5 / OQ1 = option 1).                          */
/* ------------------------------------------------------------------ */
const READY: ReadinessState = {
  certifiedSender: true,
  slugPresent: true,
  hasFieldOnForm: true,
  isSendReady: true,
};

describe('ApplicationFormShellPanel — explicit Publish (spec 12 R5 / task 6.2)', () => {
  it('renders no Publish control when onPublish is not wired', () => {
    renderPanel();
    expect(screen.queryByTestId('application-form-shell-publish')).not.toBeInTheDocument();
  });

  it('the Publish button calls the publish handler (POST /members/application-form/publish) when ready', () => {
    const onPublish = vi.fn();
    render(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        readiness={READY}
        onPublish={onPublish}
        lang="en"
      />,
    );
    const btn = screen.getByTestId('application-form-shell-publish');
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect(onPublish).toHaveBeenCalledTimes(1);
  });

  it('a plain Save does NOT publish — Save fires onSaveMail only, never onPublish (save ≠ publish)', () => {
    const onPublish = vi.fn();
    const onSaveMail = vi.fn();
    render(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        readiness={READY}
        onPublish={onPublish}
        onSaveMail={onSaveMail}
        mailDirty
        lang="en"
      />,
    );
    fireEvent.click(screen.getByTestId('application-form-shell-save-mail'));
    expect(onSaveMail).toHaveBeenCalledTimes(1);
    expect(onPublish).not.toHaveBeenCalled();
  });

  it('disables Publish and explains WHY when readiness fails (no slug / no sender / no field, R5.4)', () => {
    const onPublish = vi.fn();
    render(
      <ApplicationFormShellPanel
        values={{ ...BASE_VALUES, slug: null }}
        onChange={vi.fn()}
        readiness={{
          certifiedSender: false,
          slugPresent: false,
          hasFieldOnForm: false,
          isSendReady: false,
        }}
        onPublish={onPublish}
        lang="en"
      />,
    );
    const btn = screen.getByTestId('application-form-shell-publish');
    expect(btn).toBeDisabled();
    // A disabled button never fires the handler even if clicked.
    fireEvent.click(btn);
    expect(onPublish).not.toHaveBeenCalled();
    // The three missing preconditions are each surfaced (show, don't silently block).
    expect(screen.getByTestId('application-form-shell-publish-blocked')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-shell-publish-need-slug')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-shell-publish-need-sender')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-shell-publish-need-field')).toBeInTheDocument();
  });

  it('explains ONLY the missing precondition (a certified sender present is not listed)', () => {
    render(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        readiness={{
          certifiedSender: true,
          slugPresent: true,
          hasFieldOnForm: false, // only this is missing
          isSendReady: true,
        }}
        onPublish={vi.fn()}
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-shell-publish')).toBeDisabled();
    expect(screen.getByTestId('application-form-shell-publish-need-field')).toBeInTheDocument();
    expect(
      screen.queryByTestId('application-form-shell-publish-need-slug'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('application-form-shell-publish-need-sender'),
    ).not.toBeInTheDocument();
  });

  it('surfaces the "draft has unpublished changes" hint when ready + pending edits (save ≠ publish)', () => {
    render(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        readiness={READY}
        onPublish={vi.fn()}
        hasUnpublishedChanges
        lang="en"
      />,
    );
    expect(
      screen.getByTestId('application-form-shell-unpublished-changes'),
    ).toBeInTheDocument();
  });

  it('hides the unpublished-changes hint when the live form matches the draft', () => {
    render(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        readiness={READY}
        onPublish={vi.fn()}
        hasUnpublishedChanges={false}
        lang="en"
      />,
    );
    expect(
      screen.queryByTestId('application-form-shell-unpublished-changes'),
    ).not.toBeInTheDocument();
  });

  it('labels the button "Publish" first time and "Republish" once published', () => {
    const { rerender } = render(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        readiness={READY}
        onPublish={vi.fn()}
        everPublished={false}
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-shell-publish')).toHaveTextContent('Publish');
    rerender(
      <ApplicationFormShellPanel
        values={BASE_VALUES}
        onChange={vi.fn()}
        readiness={READY}
        onPublish={vi.fn()}
        everPublished
        lang="en"
      />,
    );
    expect(screen.getByTestId('application-form-shell-publish')).toHaveTextContent('Republish');
  });
});

/* ------------------------------------------------------------------ */
/*  Form slug display + "no public address" states (spec 12 task 6.1). */
/* ------------------------------------------------------------------ */
describe('ApplicationFormShellPanel — form slug URL states (spec 12 R4.4 / R3.3)', () => {
  it('a NAME ≠ tenant form slug shows that slug\u2019s address + open-live link', () => {
    renderPanel({ ...BASE_VALUES, slug: 'join-our-club' });
    expect(screen.getByTestId('application-form-shell-public-url')).toHaveTextContent(
      'https://join-our-club.jabaki.nl/apply',
    );
    expect(screen.getByTestId('application-form-shell-open-live')).toHaveAttribute(
      'href',
      'https://join-our-club.jabaki.nl/apply',
    );
  });

  it('states the form has no public address yet + a slug hint when no slug (not the landing editor)', () => {
    renderPanel({ ...BASE_VALUES, slug: null });
    expect(screen.getByTestId('application-form-shell-no-url')).toBeInTheDocument();
    expect(screen.getByTestId('application-form-shell-slug-hint')).toHaveTextContent(
      /form configuration/i,
    );
    expect(screen.queryByTestId('application-form-shell-open-live')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  Embed snippet ⇄ published-artifact consistency (spec 12 task 6.3). */
/* ------------------------------------------------------------------ */
describe('ApplicationFormShellPanel — embed snippet consistency with the published artifact (spec 12 R8.1)', () => {
  it('the embed snippet points at the SAME hosted URL the open-live link resolves to', () => {
    // R8.1: the external-embed snippet must address the published artifact, i.e. the same
    // `{slug}.jabaki.nl/apply` URL the "open live form" link opens — not a divergent address.
    renderPanel({ ...BASE_VALUES, embedMode: 'iframe', slug: 'hdcn-application-form' });
    const openLive = screen.getByTestId('application-form-shell-open-live');
    const snippet = screen.getByTestId('application-form-shell-iframe-snippet').textContent ?? '';
    expect(openLive).toHaveAttribute('href', 'https://hdcn-application-form.jabaki.nl/apply');
    expect(snippet).toContain('src="https://hdcn-application-form.jabaki.nl/apply"');
  });

  it('the rendered snippet carries the postMessage resize contract the published artifact emits', () => {
    // R8.1 / spec 11 E4b: the published artifact posts its height with the shared resize tokens;
    // the embed snippet's listener must validate those SAME tokens + be origin-pinned (no wildcard).
    renderPanel({ ...BASE_VALUES, embedMode: 'iframe', slug: 'hdcn-application-form' });
    const snippet = screen.getByTestId('application-form-shell-iframe-snippet').textContent ?? '';
    expect(snippet).toContain('<script>');
    expect(snippet).toContain('addEventListener("message"');
    expect(snippet).toContain(JSON.stringify(IFRAME_RESIZE_MESSAGE_TYPE));
    expect(snippet).toContain(JSON.stringify(IFRAME_RESIZE_SOURCE));
    expect(snippet).toContain(JSON.stringify(IFRAME_EMBED_ELEMENT_ID));
    // Origin-pinned to the hosted form, never a wildcard (CWE-346).
    expect(snippet).toContain('"https://hdcn-application-form.jabaki.nl"');
    expect(snippet).toContain('event.origin !== ORIGIN');
    expect(snippet).not.toContain('"*"');
  });

  it('authoring application_embed_origins persists the parsed list onto the one config#mail body', () => {
    // R8.1: the embed origins the panel authors land on the single config#mail body
    // (`application_embed_origins`) — the SAME list the published artifact's CSP frame-ancestors
    // + the public edge CORS consume. Author via the panel, assemble the body, assert it persists.
    const { onChange } = renderPanel({ ...BASE_VALUES, embedMode: 'iframe', slug: 'h-dcn' });
    fireEvent.change(screen.getByTestId('application-form-shell-embed-origins'), {
      target: { value: 'https://sites.google.com\nhttps://portal.h-dcn.nl' },
    });
    const next = onChange.mock.calls[0][0] as ShellFormValues;
    const body = toShellMailBody(next, { mail_enabled: true, mail_certified: true }, '');
    expect(body.application_embed_origins).toEqual([
      'https://sites.google.com',
      'https://portal.h-dcn.nl',
    ]);
  });
});
