import { useMutation, useQueryClient } from "@tanstack/react-query";
import { memo, useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Speaker, Transcript, Utterance, Word } from "../api/types";
import { CheckIcon, ChevronIcon, PencilIcon, SearchIcon, XIcon } from "../components/Icons";
import { SpeakerNameEditor } from "../components/SpeakerNameEditor";
import { formatClock } from "../format";
import { usePlayer, usePlayerValue } from "../hooks/player";

/** Last utterance that has started, or -1 in a long silence. Binary search: transcripts reach thousands of lines. */
function activeUtteranceIndex(utterances: Utterance[], time: number): number {
  let lo = 0;
  let hi = utterances.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if ((utterances[mid]?.start_s ?? Infinity) <= time) {
      found = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  const u = utterances[found];
  return u && time <= u.end_s + 1.5 ? found : -1;
}

function activeWordIndex(words: Word[], time: number): number {
  let found = -1;
  for (let i = 0; i < words.length; i++) {
    if ((words[i]?.start ?? Infinity) <= time) found = i;
    else break;
  }
  return found;
}

function Words({ words, active, query }: { words: Word[]; active: number; query: string }) {
  return (
    <>
      {words.map((w, i) => (
        <span
          key={i}
          data-start={w.start}
          className={`word${i === active ? " active" : ""}${query && w.text.toLowerCase().includes(query) ? " hit" : ""}`}
        >
          {w.text}{" "}
        </span>
      ))}
    </>
  );
}

/** Only the line being played subscribes to the clock, so playback does not re-render the whole transcript. */
function LiveWords({ words, query }: { words: Word[]; query: string }) {
  const active = usePlayerValue((s) => activeWordIndex(words, s.time));
  return <Words words={words} active={active} query={query} />;
}

function highlight(text: string, query: string): ReactNode {
  if (!query) return text;
  const at = text.toLowerCase().indexOf(query);
  if (at < 0) return text;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + query.length)}</mark>
      {highlight(text.slice(at + query.length), query)}
    </>
  );
}

const UtteranceRow = memo(function UtteranceRow({
  recordingId,
  utterance: u,
  speaker,
  isActive,
  query,
  isCurrentMatch,
}: {
  recordingId: string;
  utterance: Utterance;
  speaker: Speaker | undefined;
  isActive: boolean;
  query: string;
  isCurrentMatch: boolean;
}) {
  const { seek } = usePlayer();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(u.text);

  const save = useMutation({
    mutationFn: (text: string) => api.editUtterance(u.id, text),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.transcript(recordingId) });
      setEditing(false);
    },
  });

  const onTextClick = (e: MouseEvent<HTMLElement>) => {
    const start = (e.target as HTMLElement).closest<HTMLElement>("[data-start]")?.dataset.start;
    seek(start !== undefined ? Number(start) : u.start_s, true);
  };

  return (
    <div
      id={`u-${u.idx}`}
      className={`utt${isActive ? " active" : ""}${isCurrentMatch ? " current-match" : ""}`}
      data-testid="utterance"
    >
      <button className="utt-time" onClick={() => seek(u.start_s, true)} title="Play from here">
        {formatClock(u.start_s)}
      </button>
      <div className="utt-body">
        <div className="utt-head">
          {speaker ? <SpeakerNameEditor recordingId={recordingId} speaker={speaker} compact /> : <span className="muted">Unknown</span>}
          {u.has_overlap && (
            <span className="badge" title="Another speaker was talking at the same time">
              overlap
            </span>
          )}
          {u.edited && <span className="badge">edited</span>}
          {!editing && (
            <button
              className="icon-btn edit-btn"
              onClick={() => {
                setDraft(u.text);
                setEditing(true);
              }}
              aria-label="Edit text"
              title="Edit text"
            >
              <PencilIcon />
            </button>
          )}
        </div>
        {editing ? (
          <div className="utt-edit">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={Math.min(8, Math.max(2, Math.ceil(draft.length / 80)))}
              autoFocus
              aria-label="Utterance text"
            />
            <div className="row gap">
              <button className="btn small primary" disabled={save.isPending || !draft.trim()} onClick={() => save.mutate(draft)}>
                <CheckIcon size={14} /> Save
              </button>
              <button className="btn small" onClick={() => setEditing(false)}>
                Cancel
              </button>
              {save.isError && <span className="field-error">{save.error.message}</span>}
            </div>
          </div>
        ) : (
          <p className="utt-text" onClick={onTextClick}>
            {u.edited || u.words.length === 0 ? (
              highlight(u.text, query)
            ) : isActive ? (
              <LiveWords words={u.words} query={query} />
            ) : (
              <Words words={u.words} active={-1} query={query} />
            )}
          </p>
        )}
      </div>
    </div>
  );
});

export function TranscriptTab({ recordingId, transcript }: { recordingId: string; transcript: Transcript }) {
  const [query, setQuery] = useState("");
  const [follow, setFollow] = useState(true);
  const [matchPos, setMatchPos] = useState(0);
  const list = useRef<HTMLDivElement>(null);
  const { utterances } = transcript;
  const speakers = useMemo(() => new Map(transcript.speakers.map((s) => [s.id, s])), [transcript.speakers]);
  const q = query.trim().toLowerCase();
  const matches = useMemo(
    () => (q ? utterances.filter((u) => u.text.toLowerCase().includes(q)).map((u) => u.idx) : []),
    [utterances, q],
  );
  const activeIdx = usePlayerValue((s) => activeUtteranceIndex(utterances, s.time));
  const currentMatch = matches[matchPos] ?? -1;

  useEffect(() => setMatchPos(0), [q]);

  useEffect(() => {
    if (follow && activeIdx >= 0) {
      document.getElementById(`u-${activeIdx}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [activeIdx, follow]);

  useEffect(() => {
    if (currentMatch >= 0) document.getElementById(`u-${currentMatch}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [currentMatch]);

  const step = (delta: number) => {
    if (matches.length === 0) return;
    setFollow(false);
    setMatchPos((p) => (p + delta + matches.length) % matches.length);
  };

  return (
    <div className="transcript">
      <div className="transcript-tools">
        <label className="search">
          <SearchIcon />
          <input
            type="search"
            placeholder="Search this transcript"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && step(e.shiftKey ? -1 : 1)}
            aria-label="Search this transcript"
          />
          {query && (
            <button className="icon-btn" onClick={() => setQuery("")} aria-label="Clear search">
              <XIcon />
            </button>
          )}
        </label>
        {q && (
          <span className="match-nav" aria-live="polite">
            {matches.length === 0 ? "No matches" : `${matchPos + 1} of ${matches.length}`}
            <button className="icon-btn" onClick={() => step(-1)} disabled={matches.length === 0} aria-label="Previous match">
              <ChevronIcon up />
            </button>
            <button className="icon-btn" onClick={() => step(1)} disabled={matches.length === 0} aria-label="Next match">
              <ChevronIcon />
            </button>
          </span>
        )}
        <label className="follow">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow playback
        </label>
      </div>

      {utterances.length === 0 ? (
        <div className="empty small-empty">
          <h3>No speech was detected</h3>
          <p>The recording was processed, but no words were found in it.</p>
        </div>
      ) : (
        <div
          ref={list}
          className="utt-list"
          // Scrolling by hand means "stop dragging me back to the playing line".
          onWheel={() => setFollow(false)}
          onTouchMove={() => setFollow(false)}
        >
          {utterances.map((u) => (
            <UtteranceRow
              key={u.id}
              recordingId={recordingId}
              utterance={u}
              speaker={u.speaker_id ? speakers.get(u.speaker_id) : undefined}
              isActive={u.idx === activeIdx}
              query={q}
              isCurrentMatch={u.idx === currentMatch}
            />
          ))}
        </div>
      )}
    </div>
  );
}
