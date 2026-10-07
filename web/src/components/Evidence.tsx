import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { Transcript } from "../api/types";
import { formatClock } from "../format";
import { usePlayer } from "../hooks/player";

/** Lookup tables from citation ids ("u12") to the utterance and its speaker, built once per transcript. */
function useLookup(transcript: Transcript) {
  return useMemo(() => {
    const speakers = new Map(transcript.speakers.map((s) => [s.id, s]));
    const utterances = new Map(transcript.utterances.map((u) => [u.uid, u]));
    return { speakers, utterances };
  }, [transcript]);
}

const TranscriptContext = createContext<Transcript | null>(null);

export function EvidenceProvider({ transcript, children }: { transcript: Transcript; children: ReactNode }) {
  return <TranscriptContext.Provider value={transcript}>{children}</TranscriptContext.Provider>;
}

function useTranscriptCtx(): Transcript {
  const t = useContext(TranscriptContext);
  if (!t) throw new Error("EvidenceProvider is missing");
  return t;
}

/** Clickable citations: each plays the recording from the cited line. */
export function EvidenceChips({ uids, limit = 4 }: { uids: string[]; limit?: number }) {
  const transcript = useTranscriptCtx();
  const { speakers, utterances } = useLookup(transcript);
  const { seek } = usePlayer();
  const shown = uids.slice(0, limit);
  return (
    <span className="evidence">
      {shown.map((uid) => {
        const u = utterances.get(uid);
        if (!u) return null; // the line no longer exists
        const sp = u.speaker_id ? speakers.get(u.speaker_id) : undefined;
        return (
          <button
            key={uid}
            className="ev-chip"
            onClick={() => seek(u.start_s, true)}
            title={`${sp?.name ?? "Unknown"}: ${u.text}`}
            aria-label={`Play from ${formatClock(u.start_s)}: ${u.text.slice(0, 80)}`}
          >
            <i style={{ background: sp?.color ?? "var(--muted)" }} />
            {formatClock(u.start_s)}
            {sp && <span className="ev-name">{sp.name}</span>}
          </button>
        );
      })}
      {uids.length > limit && <span className="muted small">+{uids.length - limit}</span>}
    </span>
  );
}

export function useSpeakerName(transcript: Transcript, speakerId: string | null | undefined) {
  return speakerId ? transcript.speakers.find((s) => s.id === speakerId) : undefined;
}
