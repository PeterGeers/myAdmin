/**
 * Unit tests for memberTemplateService (services/memberTemplateService.ts).
 *
 * Verifies the client for the Members mail-template routes codes against the design §3 contract
 * + the API response & error standard v1.0 (steering 37). CRITICAL: the Members template routes
 * live on the SAM Members API, so the service MUST call through `membersRequest`
 * (VITE_MEMBERS_API_BASE_URL), NOT the Flask `apiService` client — the earlier bug sent bare
 * `/members/templates` to the dev server (localhost:3000), which returned index.html and left
 * the template picker empty. These tests pin that each function hits `membersRequest` with the
 * right method + path.
 *
 * `membersRequest` is mocked (no network).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { createMockResponse } from '@/test-utils/mockHelpers';

vi.mock('../membersApiService', () => ({
  membersRequest: vi.fn(),
}));

import { membersRequest } from '../membersApiService';
import {
  listMemberTemplates,
  getMemberTemplate,
  createMemberTemplate,
  updateMemberTemplate,
  deleteMemberTemplate,
  aiImproveMemberTemplate,
} from '../memberTemplateService';

const mReq = vi.mocked(membersRequest);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('memberTemplateService (routes to the Members SAM API)', () => {
  it('lists templates via GET and unwraps the standard data envelope', async () => {
    const data = [{ template_id: 't1', name: 'A' }];
    mReq.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const result = await listMemberTemplates();

    expect(mReq).toHaveBeenCalledWith('/members/templates', { method: 'GET' });
    expect(result).toEqual({ ok: true, data });
  });

  // Regression (white-page crash): the picker calls `templates.map`, so the list endpoint MUST
  // yield an array. A malformed success body is coerced to an empty array (graceful degrade).
  it('coerces a non-array `data` object on a success envelope to an empty array', async () => {
    mReq.mockResolvedValue(
      createMockResponse({ body: { success: true, data: { templates: [] } } }),
    );
    const result = await listMemberTemplates();
    expect(result).toEqual({ ok: true, data: [] });
  });

  it('coerces a success envelope with NO `data` (envelope fallback) to an empty array', async () => {
    mReq.mockResolvedValue(createMockResponse({ body: { success: true } }));
    const result = await listMemberTemplates();
    expect(result).toEqual({ ok: true, data: [] });
  });

  it('coerces a null `data` on a success envelope to an empty array', async () => {
    mReq.mockResolvedValue(createMockResponse({ body: { success: true, data: null } }));
    const result = await listMemberTemplates();
    expect(result).toEqual({ ok: true, data: [] });
  });

  it('gets a template by id via GET (URL-encoded path)', async () => {
    const data = { template_id: 'a/b', name: 'X', languages: {} };
    mReq.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const result = await getMemberTemplate('a/b');

    expect(mReq).toHaveBeenCalledWith('/members/templates/a%2Fb', { method: 'GET' });
    expect(result).toEqual({ ok: true, data });
  });

  it('creates a template via POST (JSON body)', async () => {
    const data = { template_id: 'new', name: 'New' };
    mReq.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const input = { name: 'New', languages: { en: { subject: 'S', body_html: 'B' } } };
    const result = await createMemberTemplate(input);

    expect(mReq).toHaveBeenCalledWith('/members/templates', {
      method: 'POST',
      body: JSON.stringify(input),
    });
    expect(result).toEqual({ ok: true, data });
  });

  it('updates a template via PUT (JSON body)', async () => {
    const data = { template_id: 't1', name: 'Edited' };
    mReq.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const input = { name: 'Edited', languages: { en: { subject: 'S', body_html: 'B' } } };
    const result = await updateMemberTemplate('t1', input);

    expect(mReq).toHaveBeenCalledWith('/members/templates/t1', {
      method: 'PUT',
      body: JSON.stringify(input),
    });
    expect(result).toEqual({ ok: true, data });
  });

  it('deletes a template via DELETE', async () => {
    const data = { template_id: 't1', name: 'Gone' };
    mReq.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const result = await deleteMemberTemplate('t1');

    expect(mReq).toHaveBeenCalledWith('/members/templates/t1', { method: 'DELETE' });
    expect(result).toEqual({ ok: true, data });
  });

  it('improves a template via POST to the ai-improve sub-path', async () => {
    const data = { lang: 'en', subject: 'S2', body_html: 'B2', model_used: 'x:free' };
    mReq.mockResolvedValue(createMockResponse({ body: { success: true, data } }));

    const input = { lang: 'en', instruction: 'warmer' };
    const result = await aiImproveMemberTemplate('t1', input);

    expect(mReq).toHaveBeenCalledWith('/members/templates/t1/ai-improve', {
      method: 'POST',
      body: JSON.stringify(input),
    });
    expect(result).toEqual({ ok: true, data });
  });

  it('surfaces an error envelope as a typed failure (code preserved, no throw)', async () => {
    mReq.mockResolvedValue(
      createMockResponse({
        ok: false,
        status: 422,
        body: {
          success: false,
          error: 'model not allowed',
          code: 'errors.template.aiModelDisallowed',
        },
      }),
    );

    const result = await aiImproveMemberTemplate('t1', { lang: 'en', instruction: 'x' });

    expect(result).toEqual({
      ok: false,
      status: 422,
      error: 'model not allowed',
      code: 'errors.template.aiModelDisallowed',
      params: undefined,
    });
  });

  it('treats a non-2xx with no explicit success flag as a failure', async () => {
    mReq.mockResolvedValue(createMockResponse({ ok: false, status: 500, body: {} }));

    const result = await listMemberTemplates();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(500);
    }
  });
});
