import { memo, useMemo } from "react";
import type { Transcript } from "../api/types";
import { formatClock } from "../format";
import { usePlayer, usePlayerValue } from "../hooks/player";
import { BackIcon, ForwardIcon, PauseIcon, PlayIcon } from "./Icons";

const RATES = [0.75, 1, 1.25, 1.5, 2];

function Playhead({ duration }: { duration: number }) {
  const time = usePlayerValue((s) => s.time);
  const pct = duration > 0 ? Math.min(100, (time / duration) * 100) : 0;
  return <div className="playhead" style={{ left: `${pct}%` }} />;
}

/** One lane per speaker, drawn from the diarized utterances. Click anywhere to seek. */
const Timeline = memo(function Timeline({
  transcript,
  duration,
  onSeek,
}: {
  transcript: Transcript;
  duration: number;
  onSeek: (seconds: number) => void;
}) {
  const lane = useMemo(() => new Map(transcript.speakers.map((s, i) => [s.id, i])), [transcript.speakers]);
  const color = useMemo(() => new Map(transcript.speakers.map((s) => [s.id, s.color ?? "var(--muted)"])), [transcript.speakers]);
  const lanes = Math.max(1, transcript.speakers.length);

  return (
    <div
      className="timeline"
      style={{ height: lanes * 9 + 10 }}
      role="slider"
      aria-label="Seek"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      tabIndex={-1}
      onClick={(e) => {
        const box = e.currentTarget.getBoundingClientRect();
        onSeek(((e.clientX - box.left) / box.width) * duration);
      }}
    >
      {duration > 0 &&
        transcript.utterances.map((u) => (
          <div
            key={u.id}
            className="seg"
            style={{
              left: `${(u.start_s / duration) * 100}%`,
              width: `max(2px, ${((u.end_s - u.start_s) / duration) * 100}%)`,
              top: 5 + (lane.get(u.speaker_id ?? "") ?? 0) * 9,
              background: color.get(u.speaker_id ?? "") ?? "var(--muted)",
            }}
          />
        ))}
      <Playhead duration={duration} />
    </div>
  );
});

export function PlayerBar({ transcript }: { transcript: Transcript }) {
  const { toggle, skip, seek, setRate } = usePlayer();
  const playing = usePlayerValue((s) => s.playing);
  const second = usePlayerValue((s) => Math.floor(s.time));
  const duration = usePlayerValue((s) => s.duration);
  const rate = usePlayerValue((s) => s.rate);
  const error = usePlayerValue((s) => s.error);

  return (
    <div className="player card">
      <div className="player-controls">
        <button className="icon-btn" onClick={() => skip(-10)} aria-label="Back 10 seconds" title="Back 10 s (←: 5 s)">
          <BackIcon />
        </button>
        <button className="play-btn" onClick={toggle} aria-label={playing ? "Pause" : "Play"} title="Play / pause (space)">
          {playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <button className="icon-btn" onClick={() => skip(10)} aria-label="Forward 10 seconds" title="Forward 10 s (→: 5 s)">
          <ForwardIcon />
        </button>
        <span className="clock" aria-live="off">
          {formatClock(second)} <span className="muted">/ {formatClock(duration)}</span>
        </span>
        <div className="legend">
          {transcript.speakers.map((s) => (
            <span key={s.id} className="legend-item">
              <span className="swatch" style={{ background: s.color ?? "var(--muted)" }} />
              {s.name}
            </span>
          ))}
        </div>
        <select
          className="rate"
          value={rate}
          onChange={(e) => setRate(Number(e.target.value))}
          aria-label="Playback speed"
        >
          {RATES.map((r) => (
            <option key={r} value={r}>
              {r}×
            </option>
          ))}
        </select>
      </div>
      <Timeline transcript={transcript} duration={duration} onSeek={(t) => seek(t)} />
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}
