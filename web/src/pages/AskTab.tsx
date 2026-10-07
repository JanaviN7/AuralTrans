import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api/client";
import { keys, useAskHistory, useHealth } from "../api/queries";
import type { AskTurn, Transcript } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { AlertIcon, ChatIcon, PlayIcon } from "../components/Icons";
import { formatClock } from "../format";
import { usePlayer } from "../hooks/player";

const SUGGESTIONS = ["What were the main topics?", "What was decided?", "Who is responsible for follow-ups?"];

const ABSTAIN_NOTE: Record<NonNullable<AskTurn["abstain_reason"]>, string> = {
  model_declined: "This doesn't seem to be covered in the recording.",
  no_valid_citation: "The model's answer could not be backed by a quote from the transcript, so it was withheld.",
  unsupported_answer: "The model's answer didn't match the lines it cited, so it was withheld.",
};

function Citations({ turn, transcript }: { turn: AskTurn; transcript: Transcript }) {
  const { seek } = usePlayer();
  const speakers = new Map(transcript.speakers.map((s) => [s.id, s]));
  return (
    <ul className="cites">
      {turn.citations.map((c) => {
        const sp = c.speaker_id ? speakers.get(c.speaker_id) : undefined;
        return (
          <li key={c.uid}>
            <button className="cite" onClick={() => seek(c.start_s, true)} aria-label={`Play from ${formatClock(c.start_s)}`}>
              <span className="cite-play">
                <PlayIcon />
              </span>
              <span className="cite-body">
                <span className="cite-head">
                  <span className="clock">{formatClock(c.start_s)}</span>
                  {sp && (
                    <>
                      <i className="swatch" style={{ background: sp.color ?? "var(--muted)" }} />
                      <strong>{sp.name}</strong>
                    </>
                  )}
                </span>
                <span className="cite-quote">“{c.quote}”</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function Turn({ turn, transcript }: { turn: AskTurn; transcript: Transcript }) {
  return (
    <div className="qa">
      <div className="q">{turn.question}</div>
      {turn.abstained ? (
        <div className="a abstain">
          <AlertIcon />
          <div>
            <strong>{turn.answer}</strong>
            <p className="muted small">{turn.abstain_reason ? ABSTAIN_NOTE[turn.abstain_reason] : ""}</p>
          </div>
        </div>
      ) : (
        <div className="a">
          <p>{turn.answer}</p>
          <Citations turn={turn} transcript={transcript} />
        </div>
      )}
    </div>
  );
}

export function AskTab({ recordingId, transcript }: { recordingId: string; transcript: Transcript }) {
  const qc = useQueryClient();
  const health = useHealth();
  const history = useAskHistory(recordingId, true);
  const [question, setQuestion] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (q: string) => api.ask(recordingId, q),
    onSuccess: (turn) => {
      qc.setQueryData<AskTurn[]>(keys.ask(recordingId), (old) => [...(old ?? []), turn]);
      setQuestion("");
    },
  });

  const turns = history.data ?? [];
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [turns.length, ask.isPending]);

  if (health.data && !health.data.features.ask) {
    return (
      <EmptyState icon={<ChatIcon />} title="Connect a language model to enable Ask">
        Ask answers questions using only this recording and shows the exact moments it relied on. Set <code>LLM_BASE_URL</code>,{" "}
        <code>LLM_MODEL</code> and <code>LLM_API_KEY</code> in <code>backend/.env</code> and restart the API.
      </EmptyState>
    );
  }

  const submit = (q: string) => {
    const text = q.trim();
    if (text.length >= 3 && !ask.isPending) ask.mutate(text);
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(question);
  };

  return (
    <div className="ask">
      {history.isError && <p className="field-error pad">Could not load earlier questions: {history.error.message}</p>}
      {turns.length === 0 && !ask.isPending && (
        <EmptyState icon={<ChatIcon />} title="Ask about this recording">
          Answers come only from the transcript and link to the moments they rely on. If the recording doesn't say, you'll be
          told so instead of getting a guess.
          <span className="suggest">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="btn small" onClick={() => submit(s)}>
                {s}
              </button>
            ))}
          </span>
        </EmptyState>
      )}
      <div className="qa-list">
        {turns.map((t) => (
          <Turn key={t.id} turn={t} transcript={transcript} />
        ))}
        {ask.isPending && (
          <div className="qa">
            <div className="q">{ask.variables}</div>
            <div className="a thinking">
              <span className="spinner" /> Searching the transcript…
            </div>
          </div>
        )}
        {ask.isError && (
          <div className="alert">
            <AlertIcon />
            <div>{ask.error.message}</div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      <form className="ask-form" onSubmit={onSubmit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about this recording…"
          aria-label="Question"
          maxLength={500}
        />
        <button className="btn primary" type="submit" disabled={ask.isPending || question.trim().length < 3}>
          Ask
        </button>
      </form>
    </div>
  );
}
