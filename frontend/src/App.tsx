// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/Home";
import Review from "./pages/Review";
import History from "./pages/History";
import Metrics from "./pages/Metrics";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/review" element={<Review />} />
        <Route path="/review/:noteId" element={<Review />} />
        <Route path="/history" element={<History />} />
        <Route path="/metrics" element={<Metrics />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
