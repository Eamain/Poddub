import React, { useState, useEffect } from 'react';
import { Mic2, Save, Play, Check, Loader2 } from 'lucide-react';
import { Button } from './Button';

interface Voice {
    name: string;
    id: string;
}

interface VoiceMapperProps {
    speakers: string[];
    onConfirm: (map: Record<string, string>) => void;
    isSubmitting: boolean;
}

export const VoiceMapper: React.FC<VoiceMapperProps> = ({ speakers, onConfirm, isSubmitting }) => {
    const [voices, setVoices] = useState<Voice[]>([]);
    const [voiceMap, setVoiceMap] = useState<Record<string, string>>({});
    const [loading, setLoading] = useState(true);

    // Default heuristic mapping
    const autoMapVoices = (speakerList: string[], voiceList: Voice[]) => {
        const newMap: Record<string, string> = {};
        speakerList.forEach((spk, idx) => {
            // Heuristic: Try to find name match
            const match = voiceList.find(v => v.name.toLowerCase().includes(spk.toLowerCase().replace('speaker', '').trim()));
            if (match) {
                newMap[spk] = match.id;
            } else {
                // Fallback: Cycle through voices or pick first few
                newMap[spk] = voiceList[idx % voiceList.length]?.id || "";
            }
        });
        setVoiceMap(newMap);
    };

    useEffect(() => {
        const fetchVoices = async () => {
            try {
                const res = await fetch('http://localhost:8000/api/get_voices');
                const data = await res.json();
                if (data.voices) {
                    setVoices(data.voices);
                    autoMapVoices(speakers, data.voices);
                }
            } catch (e) {
                console.error("Failed to fetch voices", e);
            } finally {
                setLoading(false);
            }
        };
        fetchVoices();
    }, [speakers]); // Refetch if speakers change? Usually stable.

    const handleVoiceChange = (speaker: string, voiceId: string) => {
        setVoiceMap(prev => ({ ...prev, [speaker]: voiceId }));
    };

    const handleConfirm = () => {
        onConfirm(voiceMap);
    };

    const [playingVoice, setPlayingVoice] = useState<string | null>(null);
    const audioRef = React.useRef<HTMLAudioElement | null>(null);

    const handlePreview = async (voiceId: string) => {
        if (!voiceId) return;
        if (playingVoice === voiceId) return; // Prevent double click

        try {
            setPlayingVoice(voiceId);
            // Append timestamp to prevent browser caching of old previews
            const res = await fetch(`http://localhost:8000/api/preview_voice?voice_id=${encodeURIComponent(voiceId)}&t=${Date.now()}`);
            if (!res.ok) throw new Error("Failed to fetch preview");

            const blob = await res.blob();
            const url = URL.createObjectURL(blob);

            if (audioRef.current) {
                audioRef.current.pause();
                audioRef.current = null;
            }

            const audio = new Audio(url);
            audioRef.current = audio;
            audio.onended = () => setPlayingVoice(null);
            audio.onerror = () => {
                setPlayingVoice(null);
                console.error("Audio playback error");
            };

            await audio.play();
        } catch (e) {
            console.error("Preview failed", e);
            setPlayingVoice(null);
        }
    };

    if (loading) return <div className="text-zinc-500 text-sm">Loading voices...</div>;

    return (
        <div className="w-full max-w-2xl mx-auto bg-zinc-900 border border-zinc-800 rounded-xl p-6 shadow-2xl animate-in fade-in slide-in-from-bottom-4">
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-semibold text-zinc-100 flex items-center gap-2">
                    <Mic2 className="w-5 h-5 text-purple-500" />
                    Assign Voices
                </h3>
                <span className="text-xs text-zinc-500">
                    Mapping {speakers.length} Speakers
                </span>
            </div>

            <div className="space-y-4 mb-8">
                {speakers.map((spk) => (
                    <div key={spk} className="flex items-center justify-between p-3 bg-zinc-950 rounded-lg border border-zinc-800/50">
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-full bg-blue-900/50 text-blue-200 flex items-center justify-center text-xs font-bold">
                                {spk.substring(0, 1)}
                            </div>
                            <span className="text-zinc-300 font-medium">{spk}</span>
                        </div>

                        <div className="flex items-center gap-3">
                            <button
                                onClick={() => handlePreview(voiceMap[spk])}
                                disabled={!voiceMap[spk] || playingVoice === voiceMap[spk]}
                                className="p-2 rounded-full hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                title="Preview Voice"
                            >
                                {playingVoice === voiceMap[spk] ? (
                                    <Loader2 className="w-4 h-4 animate-spin text-purple-500" />
                                ) : (
                                    <Play className="w-4 h-4" />
                                )}
                            </button>

                            <select
                                value={voiceMap[spk] || ""}
                                onChange={(e) => handleVoiceChange(spk, e.target.value)}
                                className="bg-zinc-800 text-sm text-zinc-200 border border-zinc-700 rounded px-3 py-2 outline-none focus:border-purple-500 min-w-[200px]"
                            >
                                <option value="" disabled>Select a Voice...</option>
                                {voices.map(v => (
                                    <option key={v.id} value={v.id}>{v.name}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                ))}
            </div>

            <div className="flex justify-end gap-3 border-t border-zinc-800 pt-4">
                <Button
                    onClick={handleConfirm}
                    isLoading={isSubmitting}
                    icon={<Check className="w-4 h-4" />}
                    className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500"
                >
                    Confirm & Generate Audio
                </Button>
            </div>
        </div>
    );
};
