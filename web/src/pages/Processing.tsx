import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Recording, Stage } from "../api/types";
import { AlertIcon, ArrowLeftIcon, CheckIcon, XIcon } from "../components/Icons";
import { formatClock } from "../format";
import { useJobEvents } from "../hooks/useJobEvents";

function StageIcon({ status }: { status: Stage["status"] }) {
  if (status === "done") return <span className="step-icon done"><CheckIcon size={14} /></span>;
  if (status === "skipped") return <span className="step-icon done" title="Reused from an earlier run"><CheckIcon size={14} /></span>;
  if (status === "failed") return <span className="step-icon failed"><XIcon size={14} /></span>;
  if (status === "running") return <span className="step-icon running"><span className="spinner" /></span>;
  return <span className="step-icon pending" />;
}

function stageNote(stage: Stage): string {
  if (stage.status === "skipped") return "reused from earlier run";
  if (stage.status === "done" || stage.status === "failed") return stage.seconds != null ? `${stage.seconds.toFixed(1)} s` : "";
  if (stage.status === "running") return "working…";
  return "";
}

export function Processing({ recording }: { recording: Recording }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [restart, setRestart] = useState(0);
  const [waited, setWaited] = useState(0);
  const { job: live } = useJobEvents(
    recording.job?.id,
    () => void qc.invalidateQueries({ queryKey: keys.recording(recording.id) }),
    restart,
  );
  const job = live ?? recording.job;

  useEffect(() => {
    const timer = setInterval(() => setWaited((w) => w + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const retry = useMutation({
    mutationFn: () => api.retryJob(recording.job!.id),
    onSuccess: () => {
      setRestart((n) => n + 1);
      setWaited(0);
      void qc.invalidateQueries({ queryKey: keys.recording(recording.id) });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteRecording(recording.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
      navigate("/");
    },
  });

  if (!job) return <p className="muted pad">This recording has no processing job.</p>;
  const failed = job.status === "failed" || recording.status === "failed";
  const stuckInQueue = job.status === "queued" && waited >= 20;
  const percent = Math.round((job.progress ?? 0) * 100);

  return (
    <div className="container narrow">
      <Link to="/" className="back-link">
        <ArrowLeftIcon /> Library
      </Link>
      <div className="card processing">
        <h1>{recording.title}</h1>
        <p className="muted">
          {failed
            ? "Processing stopped with an error."
            : job.status === "queued"
              ? "Waiting for the worker to pick this up…"
              : "Processing. You can leave this page; it keeps running and the recording will be in your library."}
        </p>

        {!failed && (
          <div className="progress" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${Math.max(percent, job.status === "running" ? 4 : 0)}%` }} />
          </div>
        )}

        <ol className="steps">
          {job.stages.map((stage) => (
            <li key={stage.name} className={`step ${stage.status}`}>
              <StageIcon status={stage.status} />
              <span className="step-label">{stage.label}</span>
              <span className="step-note">{stageNote(stage)}</span>
            </li>
          ))}
        </ol>

        {failed && (
          <div className="alert" role="alert">
            <AlertIcon />
            <div>
              <strong>{job.error ?? "Processing failed."}</strong>
              <p className="small">Finished stages are kept, so retrying continues from where it stopped.</p>
            </div>
          </div>
        )}

        {stuckInQueue && (
          <div className="alert info">
            <div>
              <strong>Still waiting for a worker ({formatClock(waited)}).</strong>
              <p className="small">
                The worker is a separate process. Start it from the backend folder with <code>python -m auraltrans.worker</code>.
              </p>
            </div>
          </div>
        )}

        <div className="row gap end">
          {failed && (
            <>
              <button className="btn" disabled={remove.isPending} onClick={() => confirm("Delete this recording?") && remove.mutate()}>
                Delete
              </button>
              <button className="btn primary" disabled={retry.isPending} onClick={() => retry.mutate()}>
                {retry.isPending ? "Retrying…" : "Retry"}
              </button>
            </>
          )}
        </div>
        {(retry.isError || remove.isError) && <p className="field-error">{(retry.error ?? remove.error)?.message}</p>}
      </div>
    </div>
  );
}
