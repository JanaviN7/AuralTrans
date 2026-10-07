import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { EXPORT_FORMATS, type ExportFormat } from "../api/types";
import { DownloadIcon, XIcon } from "./Icons";

export function ExportDialog({
  open,
  onClose,
  recordingId,
}: {
  open: boolean;
  onClose: () => void;
  recordingId: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [format, setFormat] = useState<ExportFormat>("srt");

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog ref={dialog} className="modal" onClose={onClose} onClick={(e) => e.target === dialog.current && onClose()}>
      <div className="modal-head">
        <h2>Export</h2>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <XIcon />
        </button>
      </div>
      <p className="muted small">Speaker names you set are used in every format.</p>
      <div className="format-list" role="radiogroup" aria-label="Export format">
        {EXPORT_FORMATS.map((f) => (
          <label key={f.id} className={`format ${format === f.id ? "selected" : ""}`}>
            <input type="radio" name="format" value={f.id} checked={format === f.id} onChange={() => setFormat(f.id)} />
            <span>
              <strong>{f.label}</strong>
              <span className="muted small">{f.hint}</span>
            </span>
          </label>
        ))}
      </div>
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <a
          className="btn primary"
          href={api.exportUrl(recordingId, format)}
          download
          onClick={() => setTimeout(onClose, 200)}
        >
          <DownloadIcon /> Download
        </a>
      </div>
    </dialog>
  );
}
