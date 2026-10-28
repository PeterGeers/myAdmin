/**
 * Pure draft helpers + types for {@link MemberTemplateManager}.
 *
 * Structural split out of `MemberTemplateManager.tsx` (code-quality 2026-10-28 task 10) — the
 * side-effect-free draft model (the `DraftState` shape, the blank-draft seed, and the
 * DTO⇄draft⇄request-body transforms) lives here so the component file holds the React surface
 * only. Behaviour is identical to the pre-split inline helpers — this is a pure move. The
 * component re-imports these; no public export surface changed (the component's default export,
 * `MemberTemplateManagerProps`, and `ResultField` stay exported from `MemberTemplateManager.tsx`).
 *
 * @module components/members/analytics/memberTemplateManager.helpers
 */

import type {
  MemberTemplateDto,
  MemberTemplateInput,
  TemplateKind,
} from '../../../services/memberTemplateService';

/** The two languages a mail template carries (NL/EN, R2). */
export const LANGS = ['nl', 'en'] as const;
export type Lang = (typeof LANGS)[number];

/**
 * The in-progress editor state. It carries BOTH content shapes so the one editor can switch by
 * `kind`: `languages` for a mail template, `lines` for a label template.
 */
export interface DraftState {
  /** The id of the template being edited, or `null` for a new (unsaved) draft. */
  templateId: string | null;
  /** The draft's kind — chosen on create, inferred + locked on edit. */
  kind: TemplateKind;
  name: string;
  /** MAIL content: per-language subject + body. */
  languages: Record<Lang, { subject: string; body_html: string }>;
  /** LABEL content: ordered lines, each an ordered list of 1+ field keys. */
  lines: string[][];
}

/** A blank draft of the given kind (a label draft seeds one empty starter line). */
export function emptyDraft(kind: TemplateKind = 'mail'): DraftState {
  return {
    templateId: null,
    kind,
    name: '',
    languages: {
      nl: { subject: '', body_html: '' },
      en: { subject: '', body_html: '' },
    },
    lines: [[]],
  };
}

/** The resolved kind of a DTO: an absent/undefined `kind` means a mail template. */
export function templateKind(tpl: MemberTemplateDto): TemplateKind {
  return tpl.kind === 'label' ? 'label' : 'mail';
}

/** Build a draft from a fetched template DTO (editing an existing one). Kind is inferred. */
export function draftFromTemplate(tpl: MemberTemplateDto): DraftState {
  const kind = templateKind(tpl);
  const base = emptyDraft(kind);
  const languages = { ...base.languages };
  for (const lang of LANGS) {
    const variant = tpl.languages?.[lang];
    if (variant) {
      languages[lang] = {
        subject: variant.subject ?? '',
        body_html: variant.body_html ?? '',
      };
    }
  }
  // Clone the lines so editing the draft never mutates the DTO; seed one empty line if absent.
  const lines =
    tpl.lines && tpl.lines.length > 0 ? tpl.lines.map((line) => [...line]) : [[]];
  return { templateId: tpl.template_id, kind, name: tpl.name, languages, lines };
}

/**
 * Turn a draft into the create/update request body. For a MAIL draft only languages that carry a
 * non-blank subject or body are sent (so the backend's "at least one usable language" rule is
 * satisfied). For a LABEL draft a `kind:"label"` write carries the non-empty lines + NO languages.
 */
export function draftToInput(draft: DraftState): MemberTemplateInput {
  if (draft.kind === 'label') {
    const lines = draft.lines.filter((line) => line.length > 0);
    return { name: draft.name.trim(), kind: 'label', lines };
  }
  const languages: NonNullable<MemberTemplateInput['languages']> = {};
  for (const lang of LANGS) {
    const variant = draft.languages[lang];
    if (variant.subject.trim() || variant.body_html.trim()) {
      languages[lang] = { subject: variant.subject, body_html: variant.body_html };
    }
  }
  return { name: draft.name.trim(), languages };
}
