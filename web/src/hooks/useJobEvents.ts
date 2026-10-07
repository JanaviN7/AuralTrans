import { useEffect, useRef, useState } from "react";
import type { Job } from "../api/types";

/**
 * Live job progress over Server-Sent Events. `onEnd` fires once the job is done or failed.
 * Change `restartKey` (for example after a retry) to open a fresh stream.
 * If the stream cannot connect, `live` stays false and callers fall back to polling.
 */
export function useJobEvents(jobId: string | undefined, onEnd: () => void, restartKey = 0) {
  const [job, setJob] = useState<Job | null>(null);
  const [live, setLive] = useState(false);
  const endRef = useRef(onEnd);
  endRef.current = onEnd;

  useEffect(() => {
    if (!jobId) return;
    setJob(null);
    const source = new EventSource(`/api/jobs/${jobId}/events`);
    const finish = () => {
      source.close();
      setLive(false);
      endRef.current();
    };
    source.addEventListener("open", () => setLive(true));
    source.addEventListener("progress", (e) => setJob(JSON.parse((e as MessageEvent<string>).data) as Job));
    source.addEventListener("end", finish);
    source.addEventListener("error", (e) => {
      if ("data" in e) finish(); // an application-level `event: error` from the server
      else setLive(source.readyState === EventSource.OPEN); // connection trouble: the browser retries
    });
    return () => source.close();
  }, [jobId, restartKey]);

  return { job, live };
}
