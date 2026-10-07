import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useTranscript } from "../api/queries";
import type { Recording } from "../api/types";
import { ExportDialog } from "../components/ExportDialog";
import { ArrowLeftIcon, DownloadIcon, TrashIcon } from "../components/Icons";
import { PlayerBar } from "../components/PlayerBar";
import { formatDate, formatDuration, languageName } from "../format";
import { PlayerProvider } from "../hooks/player";
import { AskTab, InsightsTab } from "./FeatureTabs";
import { SpeakersTab } from "./SpeakersTab";
import { TranscriptTab } from "./TranscriptTab";

const TABS = [
  { id: "transcript", label: "Transcript" },
  { id: "insights", label: "Insights" },
  { id: "speakers", label: "Speakers" },
  { id: "ask", label: "Ask" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export function Workspace({ recording }: { recording: Recording }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [exporting, setExporting] = useState(false);
  const transcript = useTranscript(recording.id, true);
  const tab: TabId = TABS.find((t) => t.id === params.get("tab"))?.id ?? "transcript";

  const remove = useMutation({
    mutationFn: () => api.deleteRecording(recording.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
      navigate("/");
    },
  });

  return (
    <div className="container workspace">
      <header className="ws-head">
        <Link to="/" className="back-link">
          <ArrowLeftIcon /> Library
        </Link>
        <div className="ws-title">
          <div>
            <h1>{recording.title}</h1>
            <p className="muted small">
              {formatDuration(recording.duration_s)} · {languageName(recording.language)} · {formatDate(recording.created_at)}
            </p>
          </div>
          <div className="row gap">
            <button className="btn" onClick={() => setExporting(true)}>
              <DownloadIcon /> Export
            </button>
            <button
              className="icon-btn danger"
              aria-label="Delete recording"
              title="Delete recording"
              onClick={() => confirm(`Delete "${recording.title}"? This removes the audio and transcript.`) && remove.mutate()}
            >
              <TrashIcon />
            </button>
          </div>
        </div>
      </header>

      {transcript.isPending && <p className="muted pad">Loading transcript…</p>}
      {transcript.isError && <p className="field-error pad">Could not load the transcript: {transcript.error.message}</p>}
      {transcript.data && (
        <PlayerProvider src={api.audioUrl(recording.id)} fallbackDuration={recording.duration_s}>
          <div className="sticky-player">
            <PlayerBar transcript={transcript.data} />
            <nav className="tabs" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={tab === t.id}
                  className={`tab${tab === t.id ? " active" : ""}`}
                  onClick={() => setParams(t.id === "transcript" ? {} : { tab: t.id }, { replace: true })}
                >
                  {t.label}
                </button>
              ))}
            </nav>
          </div>
          <div className="tab-panel" role="tabpanel">
            {tab === "transcript" && <TranscriptTab recordingId={recording.id} transcript={transcript.data} />}
            {tab === "insights" && <InsightsTab />}
            {tab === "speakers" && <SpeakersTab recordingId={recording.id} transcript={transcript.data} />}
            {tab === "ask" && <AskTab />}
          </div>
        </PlayerProvider>
      )}
      <ExportDialog open={exporting} onClose={() => setExporting(false)} recordingId={recording.id} />
      {remove.isError && <p className="field-error">{remove.error.message}</p>}
    </div>
  );
}
