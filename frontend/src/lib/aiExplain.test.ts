import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '../api/client';
import { AiExplainRequest } from './aiExplain';

describe('API client AI explain methods', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  describe('aiExplain', () => {
    it('returns explanation on 200', async () => {
      const mockResponse = {
        explanation: {
          whatItIs: 'A common diabetes medication',
          commonUse: 'Treating type 2 diabetes',
          plainLanguage: 'Helps control blood sugar levels',
        },
        modelUsed: 'claude-haiku-4-5-20251001',
      };

      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => mockResponse,
        })
      );

      const request: AiExplainRequest = {
        kind: 'medication',
        value: 'metformin',
      };

      const result = await api.aiExplain(request);

      expect(result).toEqual(mockResponse);
      expect(result.explanation.whatItIs).toBe('A common diabetes medication');
      expect(result.modelUsed).toBe('claude-haiku-4-5-20251001');
    });

    it('throws on 503', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: false,
          status: 503,
          json: async () => ({ error: 'AI_DISABLED' }),
        })
      );

      const request: AiExplainRequest = {
        kind: 'medication',
        value: 'metformin',
      };

      await expect(api.aiExplain(request)).rejects.toThrow('AI_DISABLED');
    });
  });

  describe('getAiStatus', () => {
    it('returns available true', async () => {
      const mockResponse = { available: true };

      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => mockResponse,
        })
      );

      const result = await api.getAiStatus();

      expect(result).toEqual(mockResponse);
      expect(result.available).toBe(true);
    });

    it('returns available false', async () => {
      const mockResponse = { available: false };

      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: async () => mockResponse,
        })
      );

      const result = await api.getAiStatus();

      expect(result).toEqual(mockResponse);
      expect(result.available).toBe(false);
    });
  });
});
