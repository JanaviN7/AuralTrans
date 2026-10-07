import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { keys, useHealth, useInsights } from "../api/queries";
import type { InsightsData, Transcript } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { EvidenceChips, useSpeakerName } from "../components/Evidence";
import { AlertIcon, SparkIcon } from "../components/Icons";
import { formatClock } from "../format";
import { usePlayer } from "../hooks/player";

type Cited = { status?: "verified" | "unverified"; evidence?: { utterance_id: string }[] };

function Weak({ item }: { item: Cited }) {
  if (item.status !== "unverified") return null;
  return (
    <span className="badge weak" title="The cited lines share little wording with this statement. Check the source before relying on it.">
      Check source
    </span>
  );
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="ins-section">
      <h3>
        {title}
        {count !== undefined && <span className="count">{count}</span>}
      </h3>
      {children}
    </section>
  );
}

function PointList({ items }: { items: (Cited & { text: string })[] }) {
  return (
    <ul className="ins-list">
      {items.map((it, i) => (
        <li key={i}>
          <span>
            {it.text} <Weak item={it} />
          </span>
          <EvidenceChips uids={(it.evidence ?? []).map((e) => e.utterance_id)} />
        </li>
      ))}
    </ul>
  );
}

function Chapters({ data, transcript }: { data: InsightsData; transcript: Transcript }) {
  const { seek } = usePlayer();
  const byUid = new Map(transcript.utterances.map((u) => [u.uid, u]));
  return (
    <ol className="chapters">
      {data.chapters.map((c, i) => {
        const start = byUid.get(c.start_uid);
        const end = byUid.get(c.end_uid);
        if (!start) return null;
        return (
          <li key={i}>
            <button className="chapter" onClick={() => seek(start.start_s, true)}>
              <span className="clock">{formatClock(start.start_s)}</span>
              <span className="chapter-title">{c.title}</span>
              {end && <span className="muted small">→ {formatClock(end.end_s)}</span>}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export function InsightsTab({ recordingId, transcript }: { recordingId: string; transcript: Transcript }) {
  const qc = useQueryClient();
  const health = useHealth();
  const insights = useInsights(recordingId, true);
  const generate = useMutation({
    mutationFn: () => api.generateInsights(recordingId),
    onSuccess: (data) => qc.setQueryData(keys.insights(recordingId), data),
  });

  if (health.data && !health.data.features.insights) {
    return (
      <EmptyState icon={<SparkIcon />} title="Connect a language model to enable Insights">
        Insights are written by a language model and checked against the transcript. Set <code>LLM_BASE_URL</code>,{" "}
        <code>LLM_MODEL</code> and <code>LLM_API_KEY</code> in <code>backend/.env</code> (Groq has a free tier) and restart the API.
        Everything else works without it.
      </EmptyState>
    );
  }
  if (insights.isPending) return <p className="muted pad">Loading insights…</p>;
  if (insights.isError) return <p className="field-error pad">Could not load insights: {insights.error.message}</p>;

  const { status, data, error } = insights.data;
  const running = status === "running" || generate.isPending;
  const button = (label: string, primary = false) => (
    <button className={`btn${primary ? " primary" : ""}`} onClick={() => generate.mutate()} disabled={running}>
      {running ? <span className="spinner" /> : <SparkIcon />} {label}
    </button>
  );

  if (!data) {
    if (running) {
      return (
        <EmptyState icon={<span className="spinner big" />} title="Reading the transcript…">
          Writing the summary, then checking every statement against the lines it cites. This usually takes under a minute.
        </EmptyState>
      );
    }
    return (
      <EmptyState icon={<SparkIcon />} title="No insights yet" action={button("Generate insights", true)}>
        A summary, key points, decisions, action items and chapters. Each one links to the exact moments in the recording, and
        anything the transcript doesn't support is dropped.
        {status === "failed" && error && <span className="field-error block">{error}</span>}
        {generate.isError && <span className="field-error block">{generate.error.message}</span>}
      </EmptyState>
    );
  }

  const unverified = Object.values(insights.data.validation?.sections ?? {}).reduce<number>(
    (n, s) => n + Number((s as { unverified?: number }).unverified ?? 0),
    0,
  );
  const dropped = Object.values(insights.data.validation?.sections ?? {}).reduce<number>(
    (n, s) => n + Number((s as { dropped_no_evidence?: number }).dropped_no_evidence ?? 0),
    0,
  );

  return (
    <div className="insights">
      <div className="ins-bar">
        <span className="muted small">
          Generated by {insights.data.model}
          {dropped > 0 && <> · {dropped} unsupported {dropped === 1 ? "statement" : "statements"} removed</>}
          {unverified > 0 && <> · {unverified} flagged “check source”</>}
        </span>
        {button(running ? "Regenerating…" : "Regenerate")}
      </div>
      {insights.data.stale && (
        <div className="notice">
          <AlertIcon /> The transcript was edited after these insights were generated. Regenerate to refresh them.
        </div>
      )}
      {status === "failed" && (
        <div className="alert">
          <AlertIcon />
          <div>The last attempt to regenerate failed{error ? `: ${error}` : "."} Showing the previous version.</div>
        </div>
      )}

      {data.summary && (
        <section className="ins-section summary-card card">
          <h3>Summary</h3>
          <p>
            {data.summary.text} <Weak item={data.summary} />
          </p>
          <EvidenceChips uids={(data.summary.evidence ?? []).map((e) => e.utterance_id)} limit={6} />
        </section>
      )}

      {data.chapters.length > 0 && (
        <Section title="Chapters" count={data.chapters.length}>
          <Chapters data={data} transcript={transcript} />
        </Section>
      )}
      {data.key_points.length > 0 && (
        <Section title="Key points" count={data.key_points.length}>
          <PointList items={data.key_points} />
        </Section>
      )}
      {data.decisions.length > 0 && (
        <Section title="Decisions" count={data.decisions.length}>
          <PointList items={data.decisions} />
        </Section>
      )}
      {data.action_items.length > 0 && (
        <Section title="Action items" count={data.action_items.length}>
          <ul className="ins-list">
            {data.action_items.map((a, i) => (
              <ActionRow key={i} item={a} transcript={transcript} />
            ))}
          </ul>
        </Section>
      )}
      {data.open_questions.length > 0 && (
        <Section title="Open questions" count={data.open_questions.length}>
          <PointList items={data.open_questions} />
        </Section>
      )}
      {!data.summary &&
        !data.chapters.length &&
        !data.key_points.length &&
        !data.decisions.length &&
        !data.action_items.length &&
        !data.open_questions.length && (
          <p className="muted pad">
            Nothing in this transcript could be backed by a quote, so nothing is shown. Try regenerating, or a different model.
          </p>
        )}
    </div>
  );
}

function ActionRow({ item, transcript }: { item: InsightsData["action_items"][number]; transcript: Transcript }) {
  const owner = useSpeakerName(transcript, item.owner_speaker_id);
  return (
    <li>
      <span>
        {item.task} <Weak item={item} />
        <span className="action-meta">
          {owner && (
            <span className="chip">
              <i className="swatch" style={{ background: owner.color ?? "var(--muted)" }} />
              {owner.name}
            </span>
          )}
          {item.due_text && <span className="chip">Due: {item.due_text}</span>}
        </span>
      </span>
      <EvidenceChips uids={(item.evidence ?? []).map((e) => e.utterance_id)} />
    </li>
  );
}
