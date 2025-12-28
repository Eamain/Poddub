import React, { memo } from 'react';
import { TranscriptSegment } from '../types';
import { User, MessageSquare } from 'lucide-react';

interface TranscriptEditorProps {
  segments: TranscriptSegment[];
  speakers: string[];
}

// Separate memoized component for each transcript segment
const TranscriptItem = memo(({ seg }: { seg: TranscriptSegment }) => {
  return (
    <div className="flex space-x-4 p-3 hover:bg-zinc-800/50 rounded-lg transition-colors">
      <div className="flex-shrink-0">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm ${seg.speaker.includes('A') || seg.speaker.toLowerCase().includes('david') ? 'bg-blue-900 text-blue-200' : 'bg-purple-900 text-purple-200'
          }`}>
          <User className="w-5 h-5" />
        </div>
        <div className="text-[10px] text-center mt-1 text-zinc-500 truncate w-10">
          {seg.speaker}
        </div>
      </div>

      <div className="flex-1 space-y-2">
        <div>
          <label className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Original (English)</label>
          <p className="text-zinc-300 text-sm leading-relaxed">{seg.originalEnglish}</p>
        </div>
        <div className="bg-zinc-950/50 p-3 rounded border border-zinc-800">
          <label className="text-xs text-emerald-600 uppercase tracking-wider font-semibold">Translation (Chinese)</label>
          <p className="text-emerald-100 font-medium text-lg leading-relaxed">{seg.translatedChinese}</p>
        </div>
      </div>
    </div>
  );
});

TranscriptItem.displayName = 'TranscriptItem';

export const TranscriptEditor: React.FC<TranscriptEditorProps> = ({ segments, speakers }) => {
  return (
    <div className="w-full max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-zinc-100 flex items-center">
          <MessageSquare className="mr-2 w-5 h-5 text-blue-500" />
          Review & Dub
        </h2>
        <div className="text-sm text-zinc-400">
          Detected Speakers: {speakers.join(", ")}
        </div>
      </div>

      <div className="bg-zinc-900 rounded-xl border border-zinc-800 overflow-hidden max-h-[60vh] overflow-y-auto">
        <div className="p-4 space-y-4">
          {segments.map((seg, idx) => (
            <TranscriptItem key={idx} seg={seg} />
          ))}
        </div>
      </div>
    </div>
  );
};
