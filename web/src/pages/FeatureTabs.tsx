import { useHealth } from "../api/queries";
import { EmptyState } from "../components/EmptyState";
import { ChatIcon, SparkIcon } from "../components/Icons";

/**
 * Insights and Ask need an LLM pipeline (summary, decisions, action items and answers that cite
 * transcript lines). That is the next phase and is not built yet, so these tabs say so plainly
 * instead of showing placeholder output. The API reports availability via /api/health.
 */
export function InsightsTab() {
  const { data } = useHealth();
  if (data?.features.insights) return null; // reserved for when the endpoint exists
  return (
    <EmptyState icon={<SparkIcon />} title="Insights are not available yet">
      Summaries, decisions, action items and chapters will appear here, each linked to the exact moment in the audio. They
      need a language model, which is the next phase of AuralTrans. The transcript, speakers and exports already work.
    </EmptyState>
  );
}

export function AskTab() {
  const { data } = useHealth();
  if (data?.features.ask) return null;
  return (
    <EmptyState icon={<ChatIcon />} title="Ask is not available yet">
      Questions about this recording, answered with timestamps you can click, will live here. They need the same language
      model setup as Insights, which is not built yet.
    </EmptyState>
  );
}
