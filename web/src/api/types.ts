import type { components } from "./schema";

type S = components["schemas"];
export type Recording = S["RecordingOut"];
export type Job = S["JobOut"];
export type Stage = S["StageOut"];
export type Speaker = S["SpeakerOut"];
export type Utterance = S["UtteranceOut"];
export type Word = S["WordOut"];
export type Transcript = S["TranscriptOut"];
export type Analytics = S["AnalyticsOut"];
export type SpeakerStats = S["SpeakerStatsOut"];
export type Health = S["HealthOut"];

export const EXPORT_FORMATS = [
  { id: "srt", label: "SRT subtitles", hint: "Timed captions with speaker names, for video players" },
  { id: "vtt", label: "WebVTT subtitles", hint: "Captions for the web, with speaker voice tags" },
  { id: "txt", label: "Plain text", hint: "[time] Speaker: text, one line per turn" },
  { id: "md", label: "Markdown report", hint: "Speaker stats table plus the full transcript" },
  { id: "json", label: "JSON", hint: "Everything, including word timestamps" },
] as const;
export type ExportFormat = (typeof EXPORT_FORMATS)[number]["id"];
