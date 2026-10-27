import { api } from '../api/client';
import { useState, useEffect } from 'react';

let _aiAvailable: boolean | null = null;
let _promise: Promise<boolean> | null = null;

export function resetAiStatusCache() {
  _aiAvailable = null;
  _promise = null;
}

export function fetchAiStatus(forceRefresh = false): Promise<boolean> {
  if (_promise === null || forceRefresh) {
    _promise = api.getAiStatus()
      .then(r => { _aiAvailable = r.available; return r.available; })
      .catch(() => { _aiAvailable = false; return false; });
  }
  return _promise;
}

export function useAiAvailable(): boolean {
  const [available, setAvailable] = useState<boolean>(_aiAvailable ?? false);
  useEffect(() => {
    fetchAiStatus(true).then(v => setAvailable(v));
  }, []);
  return available;
}
