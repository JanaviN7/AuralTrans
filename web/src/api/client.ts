import type { Analytics, ExportFormat, Health, Job, Recording, Speaker, Transcript, Utterance } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI sends {detail: string} for our errors and {detail: [{msg}]} for validation errors. */
function detailOf(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg ?? "invalid input").join("; ");
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detailOf(body, res.statusText || `Request failed (${res.status})`));
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),
  listRecordings: (q?: string, status?: string) => {
    const params = new URLSearchParams();
    if (q?.trim()) params.set("q", q.trim());
    if (status) params.set("status", status);
    const qs = params.toString();
    return request<Recording[]>(`/api/recordings${qs ? `?${qs}` : ""}`);
  },
  getRecording: (id: string) => request<Recording>(`/api/recordings/${id}`),
  deleteRecording: (id: string) => request<void>(`/api/recordings/${id}`, { method: "DELETE" }),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  retryJob: (id: string) => request<Job>(`/api/jobs/${id}/retry`, { method: "POST" }),
  getTranscript: (id: string) => request<Transcript>(`/api/recordings/${id}/transcript`),
  getAnalytics: (id: string) => request<Analytics>(`/api/recordings/${id}/analytics`),
  renameSpeaker: (recordingId: string, speakerId: string, displayName: string | null) =>
    request<Speaker>(`/api/recordings/${recordingId}/speakers/${speakerId}`, json("PATCH", { display_name: displayName })),
  editUtterance: (utteranceId: string, text: string) =>
    request<Utterance>(`/api/utterances/${utteranceId}`, json("PATCH", { text })),
  audioUrl: (id: string) => `/api/recordings/${id}/audio`,
  exportUrl: (id: string, format: ExportFormat) => `/api/recordings/${id}/export?format=${format}`,
};

export interface UploadInput {
  file: File;
  title: string;
  type: string;
  language: string;
  minSpeakers?: number;
  maxSpeakers?: number;
}

/** XMLHttpRequest rather than fetch, because fetch cannot report upload progress. */
export function uploadRecording(input: UploadInput, onProgress: (fraction: number) => void): Promise<Recording> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", input.file);
    if (input.title.trim()) form.append("title", input.title.trim());
    form.append("type", input.type);
    if (input.language !== "auto") form.append("language", input.language);
    if (input.minSpeakers) form.append("min_speakers", String(input.minSpeakers));
    if (input.maxSpeakers) form.append("max_speakers", String(input.maxSpeakers));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/recordings");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, "Could not reach the server. Is the API running?"));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* not JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Recording);
      else reject(new ApiError(xhr.status, detailOf(body, `Upload failed (${xhr.status})`)));
    };
    xhr.send(form);
  });
}
