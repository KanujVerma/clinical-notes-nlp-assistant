// frontend/src/App.tsx
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import { QueueProvider } from "./context/QueueContext";
import AppShell from "./components/AppShell";
import Upload from "./pages/Upload";
import Queue from "./pages/Queue";
import Review from "./pages/Review";
import OcrPreview from "./pages/OcrPreview";
import History from "./pages/History";
import Metrics from "./pages/Metrics";

const router = createBrowserRouter([
  {
    element: (
      <QueueProvider>
        <AppShell />
      </QueueProvider>
    ),
    children: [
      { path: "/", element: <Upload /> },
      { path: "/queue", element: <Queue /> },
      { path: "/review/:noteId", element: <Review /> },
      { path: "/review/:noteId/preview", element: <OcrPreview /> },
      { path: "/history", element: <History /> },
      { path: "/metrics", element: <Metrics /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
