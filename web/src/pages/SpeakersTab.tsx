import type { Transcript } from "../api/types";
import { useAnalytics } from "../api/queries";
import { SpeakerNameEditor } from "../components/SpeakerNameEditor";
import { formatClock } from "../format";

export function SpeakersTab({ recordingId, transcript }: { recordingId: string; transcript: Transcript }) {
  const analytics = useAnalytics(recordingId, true);

  if (analytics.isPending) return <p className="muted pad">Loading speaker statistics…</p>;
  if (analytics.isError) return <p className="field-error pad">Could not load statistics: {analytics.error.message}</p>;

  const { speakers, duration_s, silence_ratio } = analytics.data;
  const byId = new Map(transcript.speakers.map((s) => [s.id, s]));

  return (
    <div className="speakers">
      <div className="share-bar" role="img" aria-label="Share of talk time per speaker">
        {speakers.map((s) => (
          <div
            key={s.speaker_id}
            style={{ width: `${s.talk_share * 100}%`, background: s.color ?? "var(--muted)" }}
            title={`${s.name}: ${(s.talk_share * 100).toFixed(0)}%`}
          />
        ))}
      </div>
      <p className="muted small">
        {formatClock(duration_s)} total · {(silence_ratio * 100).toFixed(0)}% silence · talk time is the length of each speaker's
        utterances
      </p>

      <div className="speaker-grid">
        {speakers.map((s) => {
          const speaker = byId.get(s.speaker_id);
          return (
            <section key={s.speaker_id} className="card speaker-card">
              <header>
                {speaker ? <SpeakerNameEditor recordingId={recordingId} speaker={speaker} /> : <strong>{s.name}</strong>}
                <span className="share">{(s.talk_share * 100).toFixed(0)}%</span>
              </header>
              <div className="meter">
                <div style={{ width: `${s.talk_share * 100}%`, background: s.color ?? "var(--muted)" }} />
              </div>
              <dl>
                <div>
                  <dt>Talk time</dt>
                  <dd>{formatClock(s.talk_time_s)}</dd>
                </div>
                <div>
                  <dt>Turns</dt>
                  <dd>{s.turns}</dd>
                </div>
                <div>
                  <dt>Words / min</dt>
                  <dd>{Math.round(s.words_per_minute)}</dd>
                </div>
                <div>
                  <dt>Longest monologue</dt>
                  <dd>{formatClock(s.longest_monologue_s)}</dd>
                </div>
                <div>
                  <dt>Interruptions</dt>
                  <dd>{s.interruptions_made}</dd>
                </div>
                <div>
                  <dt>Words</dt>
                  <dd>{s.words}</dd>
                </div>
              </dl>
            </section>
          );
        })}
      </div>
    </div>
  );
}
