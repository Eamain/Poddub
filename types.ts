
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
  IDLE = 'IDLE',
  ANALYZING = 'ANALYZING', // Transcribing & Translating
  REVIEW = 'REVIEW', // User sees text
  SYNTHESIZING = 'SYNTHESIZING', // Generating Full Audio
  PREVIEWING = 'PREVIEWING', // Generating Short Preview
  PLAYBACK = 'PLAYBACK', // Finished
  ERROR = 'ERROR'
}

export type AudioSource = 'UPLOAD' | 'MICROPHONE';

export type ProgressCallback = (message: string, percent: number) => void;

export interface LogEntry {
  time: string;
  message: string;
  type: 'info' | 'success' | 'error';
}
