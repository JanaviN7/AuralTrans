import { Link, useParams } from "react-router-dom";
import { useRecording } from "../api/queries";
import { EmptyState } from "../components/EmptyState";
import { Processing } from "./Processing";
import { Workspace } from "./Workspace";

/** One URL per recording. While it is being processed this shows progress; once ready it becomes the workspace. */
export function RecordingPage() {
  const { id = "" } = useParams();
  const recording = useRecording(id);

  if (recording.isPending) return <p className="muted pad container">Loading…</p>;
  if (recording.isError) {
    return (
      <div className="container">
        <EmptyState
          title="Recording not found"
          action={
            <Link className="btn primary" to="/">
              Back to library
            </Link>
          }
        >
          {recording.error.message}
        </EmptyState>
      </div>
    );
  }
  const rec = recording.data;
  return rec.status === "ready" ? <Workspace recording={rec} /> : <Processing key={rec.job?.id} recording={rec} />;
}
