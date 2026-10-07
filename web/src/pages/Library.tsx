import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Recording } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { SearchIcon, TrashIcon, UploadIcon } from "../components/Icons";
import { StatusChip } from "../components/StatusChip";
import { formatDate, formatDuration, languageName } from "../format";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "ready", label: "Ready" },
  { id: "active", label: "In progress" },
  { id: "failed", label: "Failed" },
] as const;
type Filter = (typeof FILTERS)[number]["id"];

const matches = (r: Recording, f: Filter) =>
  f === "all" || (f === "active" ? r.status === "queued" || r.status === "processing" : r.status === f);

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function Library() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const q = useDebounced(search, 250);

  const list = useQuery({
    queryKey: keys.recordings(q, ""),
    queryFn: () => api.listRecordings(q),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "queued" || r.status === "processing") ? 3000 : false,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteRecording(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["recordings"] }),
  });

  const recordings = (list.data ?? []).filter((r) => matches(r, filter));

  return (
    <div className="container">
      <div className="page-head">
        <div>
          <h1>Library</h1>
          <p className="muted">Every recording, searchable by title and by what was said.</p>
        </div>
        <Link className="btn primary" to="/new">
          <UploadIcon size={16} /> New recording
        </Link>
      </div>

      <div className="toolbar">
        <label className="search">
          <SearchIcon />
          <input
            type="search"
            placeholder="Search titles and transcripts"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search recordings"
          />
        </label>
        <div className="seg-control" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button key={f.id} className={filter === f.id ? "on" : ""} onClick={() => setFilter(f.id)}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {list.isPending && <p className="muted pad">Loading…</p>}
      {list.isError && (
        <div className="alert" role="alert">
          <div>
            <strong>Could not reach the server.</strong>
            <p className="small">{list.error.message}. Start the API (port 8765) and try again.</p>
          </div>
        </div>
      )}

      {list.data && recordings.length === 0 && (
        <EmptyState
          icon={<UploadIcon />}
          title={q || filter !== "all" ? "Nothing matches" : "No recordings yet"}
          action={
            !q && filter === "all" ? (
              <Link className="btn primary" to="/new">
                Upload your first recording
              </Link>
            ) : undefined
          }
        >
          {q || filter !== "all"
            ? "Try a different search or filter."
            : "Upload a meeting, interview or lecture and get a transcript that shows who said what."}
        </EmptyState>
      )}

      <ul className="rec-list">
        {recordings.map((r) => (
          <li key={r.id} className="rec card">
            <Link to={`/recordings/${r.id}`} className="rec-main">
              <span className="rec-title">{r.title}</span>
              <span className="rec-meta">
                {r.status === "ready" || r.duration_s ? `${formatDuration(r.duration_s)} · ` : ""}
                {r.language ? `${languageName(r.language)} · ` : ""}
                {formatDate(r.created_at)}
              </span>
            </Link>
            {(r.status === "queued" || r.status === "processing") && r.job && (
              <div className="mini-progress" title={`${Math.round(r.job.progress * 100)}%`}>
                <div style={{ width: `${Math.max(6, r.job.progress * 100)}%` }} />
              </div>
            )}
            <StatusChip status={r.status} />
            <button
              className="icon-btn danger"
              aria-label={`Delete ${r.title}`}
              title="Delete"
              onClick={() => confirm(`Delete "${r.title}"? This removes the audio and transcript.`) && remove.mutate(r.id)}
            >
              <TrashIcon />
            </button>
          </li>
        ))}
      </ul>
      {remove.isError && <p className="field-error">{remove.error.message}</p>}
    </div>
  );
}
