import React, { useState, useEffect, useRef } from 'react';
import { Mic2, Download, Play, Pause, Languages, RotateCcw, Loader2, AlertTriangle, FileText, Save, Terminal, PlayCircle, Settings2, Sparkles } from 'lucide-react';
import { StepIndicator } from './components/StepIndicator';
import { AudioUploader } from './components/AudioUploader';
import { TranscriptEditor } from './components/TranscriptEditor';
import { Button } from './components/Button';
import { LogConsole } from './components/LogConsole';
import { AppState, ProcessedPodcast, TranscriptSegment, ProjectData, LogEntry } from './types';
import { analyzePodcastAudio, generateDubbedAudio, optimizeScriptWithGemini } from './services/geminiService';
import { decodeAudioData, concatenatePCMData, encodeMP3, encodeWAV } from './services/audioUtils';

const App: React.FC = () => {
    const [appState, setAppState] = useState<AppState>(AppState.IDLE);
    const [file, setFile] = useState<File | null>(null);

    // Data State
    const [data, setData] = useState<ProcessedPodcast>({ segments: [], detectedSpeakers: [] });
    const [audioBuffer, setAudioBuffer] = useState<AudioBuffer | null>(null);

    // Audio Playback
    const [isPlaying, setIsPlaying] = useState(false);
    const audioContextRef = useRef<AudioContext | null>(null);
    const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
    const startTimeRef = useRef<number>(0);

    // UI State
    const [error, setError] = useState<string | null>(null);
    const [progressMessage, setProgressMessage] = useState("");
    const [progressPercent, setProgressPercent] = useState(0);
    const [mp3Quality, setMp3Quality] = useState<number>(128);
    const [minimaxSettings, setMinimaxSettings] = useState({ speed: 1.0, vol: 1.0, pitch: 0 });
    const [provider, setProvider] = useState<'minimax' | 'gemini'>('minimax');
    const [isDownloading, setIsDownloading] = useState(false);
    const [isOptimizing, setIsOptimizing] = useState(false);

    // Logs
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [showLogs, setShowLogs] = useState(false);

    // Initialize AudioContext
    useEffect(() => {
        if (!audioContextRef.current) {
            audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
        }
    }, []);

    // Auto-Save Logic with Debounce
    useEffect(() => {
        if (data.segments.length > 0) {
            const timeoutId = setTimeout(() => {
                const projectToSave: ProjectData = {
                    ...data,
                    version: '1.0',
                    timestamp: Date.now()
                };
                try {
                    localStorage.setItem('poddub_autosave', JSON.stringify(projectToSave));
                    console.log(`Auto-saved ${data.segments.length} segments.`);
                } catch (e) {
                    console.error("Auto-save failed:", e);
                }
            }, 5000); // Save every 5 seconds of inactivity

            return () => clearTimeout(timeoutId);
        }
    }, [data]);

    const addLog = (message: string, type: 'info' | 'success' | 'error' = 'info') => {
        const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        setLogs(prev => [...prev, { time, message, type }]);
    };

    const handleFileSelect = async (selectedFile: File) => {
        setFile(selectedFile);
        setError(null);
        setAppState(AppState.ANALYZING);
        setProgressMessage("Uploading file to server...");
        setProgressPercent(0);
        setData({ segments: [], detectedSpeakers: [] });
        setLogs([]);
        setShowLogs(true);

        const formData = new FormData();
        formData.append('file', selectedFile);

        try {
            // 1. Upload & Start Job
            const uploadRes = await fetch('http://localhost:8000/api/process_upload', {
                method: 'POST',
                body: formData
            });
            const jobData = await uploadRes.json();

            if (!uploadRes.ok) throw new Error(jobData.error || "Upload failed");

            const jobId = jobData.job_id;
            addLog(`Job Started: ${jobId}`, 'info');

            // 2. Poll Status
            const pollInterval = setInterval(async () => {
                try {
                    const statusRes = await fetch(`http://localhost:8000/api/job_status/${jobId}`);
                    const statusData = await statusRes.json();

                    if (statusRes.ok) {
                        // Update Logs
                        if (statusData.logs && statusData.logs.length > logs.length) {
                            // This is a bit tricky with stale closure if we rely on 'logs' state
                            // Better to trust server log list or append diff? 
                            // Simplification: displaying last log message in progress
                            const lastLog = statusData.logs[statusData.logs.length - 1];
                            setProgressMessage(lastLog);

                            // Append new logs to local state 
                            // For efficiency we might not want to re-render ALL logs every second if list is huge
                            // But for now, let's just sync the last few
                        }

                        setProgressPercent(statusData.progress || 0);

                        if (statusData.status === 'completed') {
                            clearInterval(pollInterval);
                            addLog("Processing Complete! Fetching Result...", 'success');

                            // 3. Fetch Result
                            const resultRes = await fetch(`http://localhost:8000/api/get_result/${jobId}`);
                            const resultBlob = await resultRes.blob();
                            const text = await resultBlob.text();
                            const resultJson = JSON.parse(text);

                            setData({
                                segments: resultJson.segments || [],
                                detectedSpeakers: resultJson.detectedSpeakers || []
                            });
                            setAppState(AppState.REVIEW);
                        } else if (statusData.status === 'failed') {
                            clearInterval(pollInterval);
                            throw new Error(statusData.error || "Job failed");
                        }
                    }
                } catch (e: any) {
                    // Don't crash polling on transient network error, but if job failed...
                    console.error("Polling error:", e);
                }
            }, 1000);

        } catch (e: any) {
            console.error(e);
            addLog(`Error: ${e.message}`, 'error');
            setError(e.message || "Failed to process audio.");
            setAppState(AppState.IDLE); // Reset
        }
    };

    const handleProjectImport = (projectData: ProjectData) => {
        addLog("Imported project file.", 'info');
        setData({
            segments: projectData.segments,
            detectedSpeakers: projectData.detectedSpeakers
        });
        setAppState(AppState.REVIEW);
    };

    const handleOptimizeScript = async () => {
        if (!data.segments || data.segments.length === 0) return;

        setIsOptimizing(true);
        setProgressMessage("Optimizing script for colloquialism and adding AI audio tags...");
        setProgressPercent(0);
        setShowLogs(true);
        addLog("Starting AI Script Optimization...", 'info');

        try {
            const optimizedSegments = await optimizeScriptWithGemini(
                data.segments,
                (msg, percent) => {
                    setProgressMessage(msg);
                    setProgressPercent(percent);
                    if (percent % 20 === 0) addLog(msg, 'info');
                }
            );

            setData(prev => ({
                ...prev,
                segments: optimizedSegments
            }));

            addLog("Script Optimization Complete!", 'success');
        } catch (e: any) {
            console.error(e);
            addLog(`Optimization Error: ${e.message}`, 'error');
            setError("Script optimization failed. Please try again.");
        } finally {
            setIsOptimizing(false);
            setProgressMessage("");
            setProgressPercent(0);
        }
    };

    // Shared function for both Preview and Full Dub
    // Shared function for both Preview and Full Dub
    const performDubbing = async (isPreview: boolean) => {
        if (!data || data.segments.length === 0) return;

        // Stop any current playback
        if (isPlaying) togglePlayback();

        setAppState(isPreview ? AppState.PREVIEWING : AppState.SYNTHESIZING);
        setError(null);
        setProgressMessage(isPreview ? "Generating 3-minute preview..." : "Initializing full voice synthesis...");
        setProgressPercent(0);

        // MINIMAX (Backend) FLOW
        if (provider === 'minimax') {
            try {
                // If it's a preview, we might just want to generate a short snippet?
                // The current backend generate_full runs the WHOLE thing. 
                // For preview with Minimax, we might need a separate endpoint or just warn user.
                // Assuming 'Generate Full Dub' is the main use case for Minimax.

                if (isPreview) {
                    // TODO: Implement lightweight preview for Minimax
                    alert("Minimax Preview not fully implemented yet. Use Full Dub or switch to Gemini for preview.");
                    setAppState(AppState.REVIEW);
                    return;
                }

                addLog("Initiating Minimax Generation on Server...", 'info');

                const response = await fetch('http://localhost:8000/api/generate_full', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        project_name: file?.name.replace(/\.[^/.]+$/, "") || "Untitled_Project", // Approximate project name from filename
                        minimax_settings: minimaxSettings,
                        voice_map: {} // TODO: Pass actual voice map from UI
                    })
                });

                const resData = await response.json();
                if (response.ok) {
                    addLog(`Job Started: ${resData.message}`, 'success');
                    setProgressMessage("Processing on server... Check server logs for details.");
                    // In a real app, we'd poll for status. 
                    // For now, we leave it in 'SYNTHESIZING' or reset?
                    // Let's reset to REVIEW after a timeout so user isn't stuck.
                    setTimeout(() => {
                        setAppState(AppState.REVIEW);
                        alert("Background job started! The audio will appear in the output folder when done.");
                    }, 2000);
                } else {
                    throw new Error(resData.error || "Server request failed");
                }

            } catch (e: any) {
                console.error(e);
                setError(`Minimax Error: ${e.message}`);
                setAppState(AppState.REVIEW);
            }
            return;
        }

        // GEMINI (Client-Side) FLOW
        if (!isPreview) setShowLogs(true);

        const SUPER_BATCH_SIZE = isPreview ? 20 : 100;
        const allSegments = data.segments.slice(0, isPreview ? 20 : undefined);
        const totalSegments = allSegments.length;

        // Chunk the segments into Super Batches
        const superBatches: TranscriptSegment[][] = [];
        for (let i = 0; i < totalSegments; i += SUPER_BATCH_SIZE) {
            superBatches.push(allSegments.slice(i, i + SUPER_BATCH_SIZE));
        }

        const totalSuperBatches = superBatches.length;
        let completedSegments = 0;
        const allPCMChunks: Uint8Array[] = [];

        addLog(isPreview
            ? `Starting Gemini Preview Dub (${totalSegments} segments)`
            : `Starting Full Gemini Dub in ${totalSuperBatches} Parts`, 'info');

        try {
            for (let i = 0; i < totalSuperBatches; i++) {
                const batchSegments = superBatches[i];
                const partNum = i + 1;

                addLog(`Processing Part ${partNum}/${totalSuperBatches} (${batchSegments.length} segments)...`, 'info');
                setProgressMessage(`Synthesizing Part ${partNum}/${totalSuperBatches}...`);

                // Generate audio for this super-batch
                const partPCM = await generateDubbedAudio(
                    batchSegments,
                    data.detectedSpeakers,
                    (msg, percent) => {
                        // Map local batch progress to global progress
                        const batchProgress = (percent / 100) * batchSegments.length;
                        const globalPercent = ((completedSegments + batchProgress) / totalSegments) * 100;

                        setProgressPercent(globalPercent);
                        if (percent % 50 === 0) setProgressMessage(`Part ${partNum}: ${msg}`);
                    },
                    undefined
                );

                // Store this part
                allPCMChunks.push(partPCM);
                completedSegments += batchSegments.length;
                addLog(`Part ${partNum} Validated. (${Math.round(partPCM.length / 1024)} KB)`, 'success');

                // Valid delay and log
                if (!isPreview && i < totalSuperBatches - 1) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    addLog("Cooling down model...", 'info');
                }
            }

            // Merge All Parts
            addLog("Merging all audio parts...", 'info');
            setProgressMessage("Finalizing Audio...");

            if (allPCMChunks.length > 0 && audioContextRef.current) {
                const fullPCM = concatenatePCMData(allPCMChunks);
                const buffer = await decodeAudioData(fullPCM, audioContextRef.current);
                setAudioBuffer(buffer);

                setAppState(AppState.PLAYBACK);
                addLog(isPreview ? "Preview generated successfully." : "Full Podcast Generated Successfully!", 'success');

                // Auto-play preview
                if (isPreview) {
                    setTimeout(() => {
                        if (!isPlaying && sourceNodeRef.current === null) {
                            togglePlayback();
                        }
                    }, 500);
                }
            }
        } catch (e: any) {
            console.error(e);
            addLog(`Dubbing Critical Error: ${e.message}`, 'error');

            // Recovery Logic
            if (allPCMChunks.length > 0 && audioContextRef.current) {
                addLog("Recovering completed parts...", 'info');
                setError(`Dubbing interrupted at Part ${allPCMChunks.length + 1}. Saving partial result.`);
                const fullPCM = concatenatePCMData(allPCMChunks);
                const buffer = await decodeAudioData(fullPCM, audioContextRef.current);
                setAudioBuffer(buffer);
                setAppState(AppState.PLAYBACK);
            } else {
                setError(e.message || "Failed to generate audio.");
                setAppState(AppState.REVIEW);
            }
        }
    };

    const handleDownloadAudio = async () => {
        if (!audioBuffer) return;
        if (isDownloading) return;

        setIsDownloading(true);
        addLog("Starting audio conversion (this make take a moment)...", 'info');
        setProgressPercent(0);
        setProgressMessage("Converting to MP3...");

        // Give UI a moment to update state before processing starts
        await new Promise(resolve => setTimeout(resolve, 50));

        try {
            // Use the MP3 encoder with selected bitrate (async with progress)
            const blob = await encodeMP3(audioBuffer, 128, (pct) => {
                setProgressPercent(pct);
                if (pct % 20 < 1) setProgressMessage(`Converting... ${Math.round(pct)}%`);
            });

            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = 'dubbed_podcast.mp3';
            document.body.appendChild(a);
            a.click();

            // Cleanup
            setTimeout(() => {
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            }, 100);

            addLog("Download started successfully.", 'success');
        } catch (e: any) {
            console.error("Download failed:", e);
            addLog(`Download Error: ${e.message}`, 'error');
            alert("MP3 Conversion failed. Trying WAV fallback...");

            // WAV Fallback
            try {
                const wavBlob = encodeWAV(audioBuffer);
                const url = URL.createObjectURL(wavBlob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'dubbed_podcast.wav';
                a.click();
            } catch (err) {
                addLog("WAV Fallback failed too.", 'error');
            }
        } finally {
            setIsDownloading(false);
            setProgressMessage("");
            setProgressPercent(0);
        }
    };



    const handleExportScript = async () => {
        if (!data || data.segments.length === 0) return;

        addLog("Preparing script file...", 'info');
        await new Promise(resolve => setTimeout(resolve, 50));

        let content = "TRANSCRIPT & TRANSLATION\n\n";
        data.segments.forEach(seg => {
            content += `[${seg.speaker}]\n`;
            content += `EN: ${seg.originalEnglish}\n`;
            content += `CN: ${seg.translatedChinese}\n\n`;
        });

        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'poddub_script.txt';
        document.body.appendChild(a);
        a.click();

        setTimeout(() => {
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }, 100);

        addLog("Script exported successfully.", 'success');
    };

    const handleExportProject = async () => {
        if (!data) return;

        addLog("Preparing project file...", 'info');
        await new Promise(resolve => setTimeout(resolve, 50));

        const projectData: ProjectData = {
            ...data,
            version: '1.0',
            timestamp: Date.now()
        };
        const blob = new Blob([JSON.stringify(projectData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `poddub_project_${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();

        setTimeout(() => {
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }, 100);

        addLog("Project exported successfully.", 'success');
    };

    const togglePlayback = () => {
        if (!audioContextRef.current || !audioBuffer) return;

        if (isPlaying) {
            sourceNodeRef.current?.stop();
            sourceNodeRef.current = null;
            setIsPlaying(false);
        } else {
            const source = audioContextRef.current.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContextRef.current.destination);

            source.start(0);
            startTimeRef.current = audioContextRef.current.currentTime;
            sourceNodeRef.current = source;
            setIsPlaying(true);

            source.onended = () => {
                setIsPlaying(false);
            };
        }
    };

    const handleReset = () => {
        setAppState(AppState.IDLE);
        setFile(null);
        setData({ segments: [], detectedSpeakers: [] });
        setAudioBuffer(null);
        setIsPlaying(false);
        sourceNodeRef.current?.stop();
        setProgressMessage("");
        setProgressPercent(0);
        setLogs([]);
        setShowLogs(false);
        setIsOptimizing(false);
    };

    return (
        <div className="min-h-screen flex flex-col items-center p-6 sm:p-12 relative overflow-hidden bg-[#09090b]">
            {/* Background Ambience */}
            <div className="absolute top-0 left-0 w-full h-full pointer-events-none -z-10">
                <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-900/20 blur-[120px]" />
                <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-purple-900/20 blur-[120px]" />
            </div>

            {/* Header */}
            <header className="text-center mb-10 space-y-4 z-10 relative">
                <div className="flex items-center justify-center space-x-3 mb-4">
                    <div className="p-3 bg-zinc-800 rounded-xl border border-zinc-700 shadow-2xl">
                        <Mic2 className="w-8 h-8 text-blue-500" />
                    </div>
                    <div className="h-0.5 w-8 bg-zinc-700" />
                    <div className="p-3 bg-zinc-800 rounded-xl border border-zinc-700 shadow-2xl">
                        <Languages className="w-8 h-8 text-purple-500" />
                    </div>
                </div>
                <h1 className="text-4xl md:text-5xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400">
                    PodDub AI
                </h1>
                <p className="text-zinc-400 max-w-lg mx-auto text-lg">
                    Upload a long podcast to automatically transcribe, translate, and dub.
                </p>

                {/* Log Toggle */}
                <button
                    onClick={() => setShowLogs(!showLogs)}
                    className="absolute right-0 top-0 p-2 text-zinc-500 hover:text-white transition-colors"
                    title="Toggle Log Console"
                >
                    <Terminal className="w-5 h-5" />
                </button>
            </header>

            {/* Step Progress */}
            <div className="w-full max-w-3xl mb-10 z-10">
                <StepIndicator currentStep={appState} />
            </div>

            {/* Error / Warning Message */}
            {error && (
                <div className="w-full max-w-2xl mb-8 p-4 bg-amber-900/20 border border-amber-900/50 rounded-lg text-amber-200 text-center animate-in fade-in flex items-center justify-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    <span>{error}</span>
                    <Button variant="ghost" onClick={() => setError(null)} className="ml-4 h-8 text-xs">Dismiss</Button>
                </div>
            )}

            {/* Main Content Area */}
            <main className="w-full flex-1 flex flex-col items-center justify-start animate-in fade-in duration-500 z-10 pb-20">

                {appState === AppState.IDLE && (
                    <AudioUploader
                        onFileSelect={handleFileSelect}
                        onProjectImport={handleProjectImport}
                        isProcessing={false}
                    />
                )}

                {appState === AppState.ANALYZING && (
                    <div className="w-full max-w-4xl space-y-8">
                        <div className="bg-zinc-900/80 backdrop-blur-md p-6 rounded-2xl border border-zinc-800 shadow-xl sticky top-4 z-50">
                            <div className="flex justify-between text-sm text-zinc-400 mb-2">
                                <span className="flex items-center gap-2">
                                    <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                                    {progressMessage}
                                </span>
                                <span className="font-mono text-zinc-300">{Math.round(progressPercent)}%</span>
                            </div>
                            <div className="w-full h-3 bg-zinc-800 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-gradient-to-r from-blue-600 to-purple-600 transition-all duration-300 ease-out"
                                    style={{ width: `${progressPercent}%` }}
                                />
                            </div>
                        </div>

                        {/* Live Streaming Transcript */}
                        <div className="opacity-90">
                            <TranscriptEditor segments={data.segments} speakers={data.detectedSpeakers} />
                        </div>
                    </div>
                )}

                {(appState === AppState.SYNTHESIZING || appState === AppState.PREVIEWING) && (
                    <div className="text-center py-20 space-y-8 max-w-md w-full">
                        <div className="relative w-24 h-24 mx-auto">
                            <div className="absolute inset-0 border-4 border-zinc-800 rounded-full"></div>
                            <div className="absolute inset-0 border-4 border-purple-500 rounded-full border-t-transparent animate-spin"></div>
                            <div className="absolute inset-0 flex items-center justify-center">
                                <Languages className="w-8 h-8 text-purple-500 animate-pulse" />
                            </div>
                        </div>

                        <div className="space-y-3">
                            <h2 className="text-2xl font-semibold text-zinc-200">
                                {appState === AppState.PREVIEWING ? "Generating Preview" : "Synthesizing AI Dub"}
                            </h2>

                            <div className="w-full bg-zinc-800 rounded-full h-2 overflow-hidden">
                                <div
                                    className="h-full bg-purple-500 transition-all duration-300 ease-out"
                                    style={{ width: `${progressPercent}%` }}
                                ></div>
                            </div>

                            <p className="text-zinc-400 font-mono text-sm">{progressMessage}</p>
                        </div>
                    </div>
                )}

                {appState === AppState.REVIEW && data && (
                    <div className="w-full flex flex-col items-center space-y-8">
                        <div className="w-full max-w-4xl flex justify-between items-center px-4">
                            <span className="text-zinc-500 text-sm">{data.segments.length} segments loaded</span>
                            <div className="flex gap-2">
                                <Button variant="ghost" onClick={handleExportScript} icon={<FileText className="w-4 h-4" />} className="text-xs">
                                    Script (.txt)
                                </Button>
                                <Button variant="ghost" onClick={handleExportProject} icon={<Save className="w-4 h-4" />} className="text-xs">
                                    Project (.json)
                                </Button>
                            </div>
                        </div>

                        {isOptimizing && (
                            <div className="sticky top-4 z-50 w-full max-w-4xl bg-zinc-900/90 backdrop-blur border border-purple-500/50 p-4 rounded-xl shadow-2xl animate-in slide-in-from-top-4">
                                <div className="flex justify-between items-center mb-2">
                                    <span className="text-purple-300 flex items-center gap-2 text-sm font-semibold">
                                        <Sparkles className="w-4 h-4 animate-spin-slow" />
                                        AI Optimizing Script...
                                    </span>
                                    <span className="text-xs text-zinc-400">{Math.round(progressPercent)}%</span>
                                </div>
                                <div className="w-full bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                                    <div className="h-full bg-purple-500 transition-all duration-300" style={{ width: `${progressPercent}%` }} />
                                </div>
                            </div>
                        )}

                        <TranscriptEditor segments={data.segments} speakers={data.detectedSpeakers} />

                        <div className="sticky bottom-8 flex gap-4 bg-zinc-950/90 p-4 rounded-full border border-zinc-800 shadow-2xl backdrop-blur-xl">
                            {/* Minimax Settings */}
                            <div className="flex flex-col justify-center gap-1 mr-2 bg-zinc-900 p-2 rounded-lg border border-zinc-800">
                                <div className="flex items-center justify-between mb-1">
                                    <select
                                        value={provider}
                                        onChange={(e) => setProvider(e.target.value as any)}
                                        className="bg-zinc-800 text-[10px] text-zinc-300 border-none rounded px-1 py-0.5 outline-none cursor-pointer hover:bg-zinc-700"
                                    >
                                        <option value="minimax">Minimax</option>
                                        <option value="gemini">Gemini</option>
                                    </select>
                                </div>

                                {provider === 'minimax' && (
                                    <>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-zinc-500 w-8">Spd</span>
                                            <input
                                                type="range" min="0.5" max="1.5" step="0.1"
                                                value={minimaxSettings.speed}
                                                onChange={e => setMinimaxSettings({ ...minimaxSettings, speed: parseFloat(e.target.value) })}
                                                className="w-16 h-1 bg-zinc-700 rounded appearance-none accent-purple-500"
                                                title={`Speed: ${minimaxSettings.speed}`}
                                            />
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-zinc-500 w-8">Vol</span>
                                            <input
                                                type="range" min="0.5" max="2.0" step="0.1"
                                                value={minimaxSettings.vol}
                                                onChange={e => setMinimaxSettings({ ...minimaxSettings, vol: parseFloat(e.target.value) })}
                                                className="w-16 h-1 bg-zinc-700 rounded appearance-none accent-blue-500"
                                                title={`Volume: ${minimaxSettings.vol}`}
                                            />
                                        </div>
                                    </>
                                )}
                            </div>

                            <Button variant="secondary" onClick={handleReset}>Start Over</Button>

                            <Button
                                variant="secondary"
                                onClick={handleOptimizeScript}
                                icon={<Sparkles className="w-4 h-4 text-purple-400" />}
                                isLoading={isOptimizing}
                                disabled={isOptimizing}
                                className="border-purple-500/30 hover:bg-purple-500/10 hover:text-purple-300"
                            >
                                AI Optimize
                            </Button>

                            <Button
                                variant="secondary"
                                onClick={() => performDubbing(true)}
                                icon={<PlayCircle className="w-5 h-5" />}
                                title="Generate first 20 segments (~2 mins)"
                            >
                                Test Dub (Preview)
                            </Button>

                            <Button
                                onClick={() => performDubbing(false)}
                                className="px-8"
                                loading={appState === AppState.SYNTHESIZING} // Fixed loading prop
                                icon={<Languages className="w-5 h-5" />}
                            >
                                Generate Full Dub
                            </Button>
                        </div>
                    </div>
                )}

                {appState === AppState.PLAYBACK && audioBuffer && (
                    <div className="w-full max-w-md mx-auto text-center space-y-8 py-10 bg-zinc-900/50 rounded-2xl border border-zinc-800 p-8 backdrop-blur-sm">
                        <div className="space-y-2">
                            <h2 className="text-3xl font-bold text-white">Dubbing Complete!</h2>
                            <p className="text-zinc-400">
                                {audioBuffer.duration < 200 ? "Preview ready." : "Full podcast ready."}
                            </p>
                            <p className="text-xs text-zinc-500">Duration: {Math.floor(audioBuffer.duration / 60)}m {Math.floor(audioBuffer.duration % 60)}s</p>
                        </div>

                        <div className="flex justify-center py-8">
                            <button
                                onClick={togglePlayback}
                                className="w-24 h-24 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center shadow-lg hover:scale-105 transition-transform group"
                            >
                                {isPlaying ? (
                                    <Pause className="w-10 h-10 text-white fill-current" />
                                ) : (
                                    <Play className="w-10 h-10 text-white fill-current ml-1" />
                                )}
                            </button>
                        </div>

                        <div className="space-y-4">
                            <div className="flex items-center justify-center space-x-2 bg-zinc-800/50 p-2 rounded-lg">
                                <Settings2 className="w-4 h-4 text-zinc-400" />
                                <span className="text-xs text-zinc-400">Quality:</span>
                                <select
                                    value={mp3Quality}
                                    onChange={(e) => setMp3Quality(Number(e.target.value))}
                                    className="bg-zinc-900 border border-zinc-700 text-xs rounded px-2 py-1 text-zinc-200 outline-none focus:border-blue-500"
                                >
                                    <option value={64}>Low (64 kbps)</option>
                                    <option value={128}>Medium (128 kbps)</option>
                                    <option value={192}>High (192 kbps)</option>
                                    <option value={320}>Ultra (320 kbps)</option>
                                </select>
                            </div>

                            <div className="flex justify-center space-x-4">
                                {/* If it's a short preview (less than 5 mins for safety), show 'Back to Review' prominently */}
                                {audioBuffer.duration < 300 && (
                                    <Button variant="secondary" onClick={() => setAppState(AppState.REVIEW)}>
                                        Back to Review
                                    </Button>
                                )}

                                <Button onClick={handleDownloadAudio} isLoading={isDownloading}>
                                    <Download className="w-4 h-4 mr-2" /> Download Audio
                                </Button>

                                {audioBuffer.duration > 300 && (
                                    <Button variant="ghost" onClick={handleReset} icon={<RotateCcw className="w-4 h-4" />}>
                                        New Project
                                    </Button>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </main>

            {/* Log Console Drawer */}
            <LogConsole logs={logs} isOpen={showLogs} onClose={() => setShowLogs(false)} />
        </div>
    );
};

export default App;
