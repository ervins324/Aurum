import { useEffect, useState } from "react";

const STORAGE_KEY = "aurum_exclude_transfers";
const listeners = new Set<(val: boolean) => void>();

function readStored(): boolean {
  return localStorage.getItem(STORAGE_KEY) === "true";
}

/** Reactive hook for toggling whether money transfers / wire operations
 *  are excluded from cash flow, dashboard summaries, and reports.
 *  Persisted in localStorage and synchronised across all components. */
export function useExcludeTransfers() {
  const [excludeTransfers, setExcludeTransfersState] = useState<boolean>(readStored);

  useEffect(() => {
    const handler = (val: boolean) => setExcludeTransfersState(val);
    listeners.add(handler);
    return () => {
      listeners.delete(handler);
    };
  }, []);

  const setExcludeTransfers = (val: boolean) => {
    setExcludeTransfersState(val);
    localStorage.setItem(STORAGE_KEY, String(val));
    listeners.forEach((listener) => listener(val));
  };

  return [excludeTransfers, setExcludeTransfers] as const;
}
