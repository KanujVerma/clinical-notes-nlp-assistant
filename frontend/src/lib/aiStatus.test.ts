import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

// Reset module-level cache between tests
beforeEach(async () => {
  vi.resetModules();
});

describe('useAiAvailable', () => {
  it('returns false initially', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ available: true }),
    }));
    const { useAiAvailable } = await import('./aiStatus');
    const { result } = renderHook(() => useAiAvailable());
    expect(result.current).toBe(false); // starts false before resolve
  });

  it('returns true after status resolves as available', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ available: true }),
    }));
    const { useAiAvailable } = await import('./aiStatus');
    const { result } = renderHook(() => useAiAvailable());
    await act(async () => { await new Promise(r => setTimeout(r, 0)); });
    expect(result.current).toBe(true);
  });

  it('returns false when AI is not available', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ available: false }),
    }));
    const { useAiAvailable } = await import('./aiStatus');
    const { result } = renderHook(() => useAiAvailable());
    await act(async () => { await new Promise(r => setTimeout(r, 0)); });
    expect(result.current).toBe(false);
  });

  it('returns false when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')));
    const { useAiAvailable } = await import('./aiStatus');
    const { result } = renderHook(() => useAiAvailable());
    await act(async () => { await new Promise(r => setTimeout(r, 0)); });
    expect(result.current).toBe(false);
  });
});
