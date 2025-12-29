import React, { memo } from 'react';
import { TranscriptSegment } from '../types';
import { User, MessageSquare } from 'lucide-react';

interface TranscriptEditorProps {
  segments: TranscriptSegment[];
  speakers: string[];
  activeSegmentIndex?: number;
}

// Separate memoized component for each transcript segment
const TranscriptItem = memo(({ seg, isActive, id }: { seg: TranscriptSegment, isActive: boolean, id: string }) => {
  return (
    <div id={id} className={`flex space-x-4 p-3 rounded-lg transition-all duration-300 border-2 ${isActive
      ? 'bg-blue-900/30 border-blue-500/50 shadow-[0_0_30px_rgba(59,130,246,0.15)] scale-[1.02]'
      : 'hover:bg-zinc-800/50 border-transparent opacity-60' // Dim inactive items slightly
      }`}>
      <div className="flex-shrink-0">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-transform duration-300 ${isActive ? 'scale-110' : ''
          } ${seg.speaker.includes('A') || seg.speaker.toLowerCase().includes('david') ? 'bg-blue-900 text-blue-200' : 'bg-purple-900 text-purple-200'
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
          <p className={`text-sm leading-relaxed transition-colors ${isActive ? 'text-white' : 'text-zinc-400'}`}>{seg.originalEnglish}</p>
        </div>
        <div className={`p-3 rounded border transition-colors ${isActive ? 'bg-zinc-950/80 border-blue-500/30' : 'bg-zinc-950/30 border-zinc-800'
          }`}>
          <label className="text-xs text-emerald-600 uppercase tracking-wider font-semibold">Translation (Chinese)</label>
          <p className={`font-medium text-lg leading-relaxed transition-colors ${isActive ? 'text-emerald-100' : 'text-emerald-200/60'
            }`}>{seg.translatedChinese}</p>
        </div>
      </div>
    </div>
  );
});

TranscriptItem.displayName = 'TranscriptItem';

export const TranscriptEditor: React.FC<TranscriptEditorProps> = ({ segments, speakers, activeSegmentIndex }) => {
  // Auto-scroll to active segment
  React.useEffect(() => {
    if (typeof activeSegmentIndex === 'number' && activeSegmentIndex >= 0) {
      const el = document.getElementById(`seg-${activeSegmentIndex}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [activeSegmentIndex]);

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

      <div className="space-y-4">
        {segments.map((seg, idx) => (
          <TranscriptItem
            key={idx}
            seg={seg}
            id={`seg-${idx}`}
            isActive={idx === activeSegmentIndex}
          />
        ))}
      </div>
    </div>
  );
};
