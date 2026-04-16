// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueueProvider } from "./context/QueueContext";
import AppShell from "./components/AppShell";
import Upload from "./pages/Upload";
import Queue from "./pages/Queue";
import Review from "./pages/Review";
import OcrPreview from "./pages/OcrPreview";
import History from "./pages/History";
import Metrics from "./pages/Metrics";

export default function App() {
  return (
    <BrowserRouter>
      <QueueProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Upload />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/review/:noteId" element={<Review />} />
            <Route path="/review/:noteId/preview" element={<OcrPreview />} />
            <Route path="/history" element={<History />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </QueueProvider>
    </BrowserRouter>
  );
}
