import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Speaker } from "../api/types";
import { CheckIcon, PencilIcon, XIcon } from "./Icons";

/** Click a speaker's name to rename it everywhere. An empty name restores "Speaker N". */
export function SpeakerNameEditor({
  recordingId,
  speaker,
  compact,
}: {
  recordingId: string;
  speaker: Speaker;
  compact?: boolean;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(speaker.display_name ?? "");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) input.current?.select();
  }, [editing]);

  const rename = useMutation({
    mutationFn: (name: string | null) => api.renameSpeaker(recordingId, speaker.id, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.transcript(recordingId) });
      void qc.invalidateQueries({ queryKey: keys.analytics(recordingId) });
      setEditing(false);
    },
  });

  const save = () => {
    const trimmed = value.trim();
    if (trimmed === (speaker.display_name ?? "")) setEditing(false);
    else rename.mutate(trimmed || null);
  };

  if (!editing) {
    return (
      <button
        className={`speaker-name ${compact ? "compact" : ""}`}
        onClick={() => {
          setValue(speaker.display_name ?? "");
          setEditing(true);
        }}
        title="Rename speaker"
      >
        <span className="swatch" style={{ background: speaker.color ?? "var(--muted)" }} />
        <span className="speaker-label">{speaker.name}</span>
        <span className="edit-hint">
          <PencilIcon />
        </span>
      </button>
    );
  }
  return (
    <span className="speaker-edit">
      <span className="swatch" style={{ background: speaker.color ?? "var(--muted)" }} />
      <input
        ref={input}
        value={value}
        maxLength={80}
        placeholder="Name"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") setEditing(false);
        }}
        aria-label="Speaker name"
      />
      <button className="icon-btn" onClick={save} disabled={rename.isPending} aria-label="Save name">
        <CheckIcon />
      </button>
      <button className="icon-btn" onClick={() => setEditing(false)} aria-label="Cancel">
        <XIcon />
      </button>
      {rename.isError && <span className="field-error">{rename.error.message}</span>}
    </span>
  );
}
