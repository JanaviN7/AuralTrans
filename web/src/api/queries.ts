import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export const keys = {
  recordings: (q: string, status: string) => ["recordings", q, status] as const,
  recording: (id: string) => ["recording", id] as const,
  transcript: (id: string) => ["transcript", id] as const,
  analytics: (id: string) => ["analytics", id] as const,
  health: ["health"] as const,
};

export const useHealth = () => useQuery({ queryKey: keys.health, queryFn: api.health, staleTime: 60_000 });

export const useRecording = (id: string) =>
  useQuery({
    queryKey: keys.recording(id),
    queryFn: () => api.getRecording(id),
    // Safety net behind the SSE stream: keep checking while the recording is still being processed.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "processing" ? 3000 : false;
    },
  });

export const useTranscript = (id: string, enabled: boolean) =>
  useQuery({ queryKey: keys.transcript(id), queryFn: () => api.getTranscript(id), enabled });

export const useAnalytics = (id: string, enabled: boolean) =>
  useQuery({ queryKey: keys.analytics(id), queryFn: () => api.getAnalytics(id), enabled });
