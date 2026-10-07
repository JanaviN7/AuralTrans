import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { uploadRecording } from "../api/client";
import { ArrowLeftIcon, UploadIcon, XIcon } from "../components/Icons";
import { LANGUAGES, formatBytes } from "../format";

const ACCEPT = ".wav,.mp3,.m4a,.mp4,.webm";
const TYPES = [
  ["meeting", "Meeting"],
  ["interview", "Interview"],
  ["lecture", "Lecture"],
  ["call", "Call"],
] as const;
const MAX_MB = 500;

export function NewRecording() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const picker = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [type, setType] = useState("meeting");
  const [language, setLanguage] = useState("auto");
  const [minSpeakers, setMin] = useState("");
  const [maxSpeakers, setMax] = useState("");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const choose = (f: File | undefined) => {
    if (!f) return;
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPT.split(",").includes(ext)) return setError(`${ext || "That file type"} is not supported. Use WAV, MP3, M4A, MP4 or WebM.`);
    if (f.size > MAX_MB * 1024 * 1024) return setError(`That file is larger than ${MAX_MB} MB.`);
    setError(null);
    setFile(f);
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ""));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    choose(e.dataTransfer.files[0]);
  };

  const min = Number(minSpeakers) || undefined;
  const max = Number(maxSpeakers) || undefined;
  const hintInvalid = !!min && !!max && min > max;
  const uploading = progress !== null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file || hintInvalid) return;
    setError(null);
    setProgress(0);
    try {
      const rec = await uploadRecording({ file, title, type, language, minSpeakers: min, maxSpeakers: max }, setProgress);
      void qc.invalidateQueries({ queryKey: ["recordings"] });
      navigate(`/recordings/${rec.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setProgress(null);
    }
  };

  return (
    <div className="container narrow">
      <Link to="/" className="back-link">
        <ArrowLeftIcon /> Library
      </Link>
      <form className="card form" onSubmit={submit}>
        <h1>New recording</h1>

        {!file ? (
          <div
            className={`dropzone${dragging ? " dragging" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => picker.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && picker.current?.click()}
          >
            <UploadIcon />
            <strong>Drop an audio or video file here</strong>
            <span className="muted small">or click to choose · WAV, MP3, M4A, MP4, WebM · up to {MAX_MB} MB</span>
          </div>
        ) : (
          <div className="file-chip">
            <div>
              <strong>{file.name}</strong>
              <span className="muted small"> · {formatBytes(file.size)}</span>
            </div>
            {!uploading && (
              <button type="button" className="icon-btn" onClick={() => setFile(null)} aria-label="Remove file">
                <XIcon />
              </button>
            )}
          </div>
        )}
        <input
          ref={picker}
          type="file"
          accept={ACCEPT}
          hidden
          data-testid="file-input"
          onChange={(e) => {
            choose(e.target.files?.[0]);
            e.target.value = "";
          }}
        />

        <label className="field">
          <span>Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Weekly sync" maxLength={200} disabled={uploading} />
        </label>

        <div className="field-row">
          <label className="field">
            <span>Type</span>
            <select value={type} onChange={(e) => setType(e.target.value)} disabled={uploading}>
              {TYPES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Language</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value)} disabled={uploading}>
              {LANGUAGES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="field speakers-hint" disabled={uploading}>
          <legend>Number of speakers (optional)</legend>
          <p className="muted small">Leave empty to detect it automatically. A range helps when you know it.</p>
          <div className="field-row">
            <label className="field">
              <span>At least</span>
              <input type="number" min={1} max={20} value={minSpeakers} onChange={(e) => setMin(e.target.value)} placeholder="auto" />
            </label>
            <label className="field">
              <span>At most</span>
              <input type="number" min={1} max={20} value={maxSpeakers} onChange={(e) => setMax(e.target.value)} placeholder="auto" />
            </label>
          </div>
          {hintInvalid && <p className="field-error">"At least" cannot be larger than "At most".</p>}
        </fieldset>

        <p className="muted small">Your audio stays on this machine. Nothing is sent to an outside service.</p>

        {uploading && (
          <div className="progress" role="progressbar" aria-valuenow={Math.round((progress ?? 0) * 100)}>
            <div style={{ width: `${Math.round((progress ?? 0) * 100)}%` }} />
          </div>
        )}
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}

        <div className="row gap end">
          <Link className="btn" to="/">
            Cancel
          </Link>
          <button className="btn primary" type="submit" disabled={!file || uploading || hintInvalid}>
            {uploading ? (progress !== null && progress >= 1 ? "Starting…" : "Uploading…") : "Upload and transcribe"}
          </button>
        </div>
      </form>
    </div>
  );
}
