// frontend/src/context/QueueContext.tsx
import { createContext, useContext, useState, useCallback } from "react";

interface QueueContextValue {
  queueVersion: number;
  bumpQueue: () => void;
}

const QueueContext = createContext<QueueContextValue>({
  queueVersion: 0,
  bumpQueue: () => {},
});

export function QueueProvider({ children }: { children: React.ReactNode }) {
  const [queueVersion, setQueueVersion] = useState(0);
  const bumpQueue = useCallback(() => setQueueVersion((v) => v + 1), []);

  return (
    <QueueContext.Provider value={{ queueVersion, bumpQueue }}>
      {children}
    </QueueContext.Provider>
  );
}

export function useQueue() {
  return useContext(QueueContext);
}
