import { Link, Navigate, Route, Routes } from "react-router-dom";
import { Logo } from "./components/Icons";
import { Library } from "./pages/Library";
import { NewRecording } from "./pages/NewRecording";
import { RecordingPage } from "./pages/RecordingPage";

export function App() {
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          <Logo /> AuralTrans
        </Link>
        <span className="muted small">Speaker-attributed transcripts</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/new" element={<NewRecording />} />
          <Route path="/recordings/:id" element={<RecordingPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
