import React from 'react';
import { Loader2, CheckCircle2, FileText, Music, Sparkles, Mic2 } from 'lucide-react';

interface StageProgress {
    status: 'pending' | 'active' | 'completed';
    percent?: number;
    current?: number;
    total?: number;
    outline?: boolean;
    summary?: boolean;
}

interface ProgressStackProps {
    stages: {
        transcribe: StageProgress;
        polish: StageProgress;
        analysis: StageProgress;
        generate: StageProgress;
    };
    currentPhase: 'analysis' | 'review' | 'generation';
}

export const ProgressStack: React.FC<ProgressStackProps> = ({ stages, currentPhase }) => {
    const getStatusIcon = (stage: StageProgress) => {
        if (stage.status === 'completed') return <CheckCircle2 className="w-5 h-5 text-emerald-400" />;
        if (stage.status === 'active') return <Loader2 className="w-5 h-5 animate-spin text-blue-400" />;
        return <div className="w-5 h-5 rounded-full border-2 border-zinc-700" />;
    };

    const getOpacity = (stage: StageProgress) => stage.status === 'pending' ? 'opacity-40' : 'opacity-100';

    return (
        <div className="w-full max-w-2xl mx-auto space-y-4 bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800 backdrop-blur-sm">
            <h3 className="text-zinc-400 text-sm font-semibold uppercase tracking-wider mb-4">Pipeline Progress</h3>

            {/* 1. Transcribe */}
            <div className={`flex items-center gap-4 ${getOpacity(stages.transcribe)} transition-all`}>
                <div className="p-2 bg-blue-900/30 rounded-lg">
                    <Mic2 className="w-5 h-5 text-blue-400" />
                </div>
                <div className="flex-1 space-y-1">
                    <div className="flex justify-between text-sm">
                        <span className="text-zinc-200">Audio Transcription</span>
                        <span className="text-zinc-400">{stages.transcribe.percent || 0}%</span>
                    </div>
                    <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${stages.transcribe.percent || 0}%` }} />
                    </div>
                </div>
                {getStatusIcon(stages.transcribe)}
            </div>

            {/* 2. Polish */}
            <div className={`flex items-center gap-4 ${getOpacity(stages.polish)} transition-all`}>
                <div className="p-2 bg-purple-900/30 rounded-lg">
                    <Sparkles className="w-5 h-5 text-purple-400" />
                </div>
                <div className="flex-1 space-y-1">
                    <div className="flex justify-between text-sm">
                        <span className="text-zinc-200">Contextual Refinement</span>
                        <span className="text-zinc-400">{stages.polish.percent || 0}%</span>
                    </div>
                    <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full bg-purple-500 transition-all duration-500" style={{ width: `${stages.polish.percent || 0}%` }} />
                    </div>
                </div>
                {getStatusIcon(stages.polish)}
            </div>

            {/* 3. Analysis - Only show in Review or Generation phase */}
            {(currentPhase === 'review' || currentPhase === 'generation') && (
                <div className={`flex items-center gap-4 ${getOpacity(stages.analysis)} transition-all animate-in fade-in slide-in-from-top-2`}>
                    <div className="p-2 bg-amber-900/30 rounded-lg">
                        <FileText className="w-5 h-5 text-amber-400" />
                    </div>
                    <div className="flex-1">
                        <div className="flex items-center justify-between text-sm mb-1">
                            <span className="text-zinc-200">Content Analysis</span>
                            {stages.analysis.status === 'completed' && <span className="text-amber-400 text-xs">Analysis Ready</span>}
                        </div>
                        <div className="flex gap-2">
                            <div className={`px-2 py-1 rounded text-xs border ${stages.analysis.outline ? 'bg-amber-500/20 border-amber-500/50 text-amber-200' : 'bg-zinc-800 border-zinc-700 text-zinc-500'}`}>
                                Outline
                            </div>
                            <div className={`px-2 py-1 rounded text-xs border ${stages.analysis.summary ? 'bg-amber-500/20 border-amber-500/50 text-amber-200' : 'bg-zinc-800 border-zinc-700 text-zinc-500'}`}>
                                Summary
                            </div>
                        </div>
                    </div>
                    {getStatusIcon(stages.analysis)}
                </div>
            )}

            {/* 4. Generation - Only show in Generation phase */}
            {currentPhase === 'generation' && (
                <div className={`flex items-center gap-4 ${getOpacity(stages.generate)} transition-all animate-in fade-in slide-in-from-top-2`}>
                    <div className="p-2 bg-green-900/30 rounded-lg">
                        <Music className="w-5 h-5 text-green-400" />
                    </div>
                    <div className="flex-1 space-y-1">
                        <div className="flex justify-between text-sm">
                            <span className="text-zinc-200">Audio Synthesis</span>
                            <span className="text-zinc-400">{stages.generate.percent || 0}%</span>
                        </div>
                        <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                            <div className="h-full bg-green-500 transition-all duration-500" style={{ width: `${stages.generate.percent || 0}%` }} />
                        </div>
                    </div>
                    {getStatusIcon(stages.generate)}
                </div>
            )}

        </div>
    );
};
