
export interface TranscriptSegment {
  speaker: string; // "Speaker A", "Speaker B", etc.
  originalEnglish: string;
  translatedChinese: string;
}

export interface ProcessedPodcast {
  segments: TranscriptSegment[];
  detectedSpeakers: string[];
}

export interface ProjectData extends ProcessedPodcast {
  version: string;
  timestamp: number;
}

export enum AppState {
  IDLE = 'idle',
  ANALYZING = 'analyzing', // Transcribing & Translating
  REVIEW = 'review', // User sees text
  GENERATING = 'generating', // Generating Full Audio
  PREVIEWING = 'previewing', // Generating Short Preview
  PLAYBACK = 'playback', // Finished
  ERROR = 'error'
}

export type AudioSource = 'UPLOAD' | 'MICROPHONE';

export type ProgressCallback = (message: string, percent: number) => void;

export interface LogEntry {
  time: string;
  message: string;
  type: 'info' | 'success' | 'error';
}
