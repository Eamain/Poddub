
import React, { useState } from 'react';
import { FileText, Download, FileAudio, RefreshCw } from 'lucide-react';
import { Button } from './Button';

interface DownloadFile {
    name: string;
    type: string;
    size: number;
}

interface DownloadListProps {
    files: DownloadFile[];
    jobId: string;
    onRefresh?: () => void;
}

export const DownloadList: React.FC<DownloadListProps> = ({ files, jobId, onRefresh }) => {
    const [generating, setGenerating] = useState<string | null>(null);

    const handleDownload = (filename: string) => {
        const url = `http://localhost:8000/api/download_file/${jobId}?file=${encodeURIComponent(filename)}`;
        window.open(url, '_blank');
    };

    const handleGenerate = async (type: 'outline' | 'summary') => {
        setGenerating(type);
        try {
            await fetch('http://localhost:8000/api/generate_doc', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: jobId, doc_type: type })
            });
            // Wait a bit for file to be created then refresh
            // Poll for 10 seconds
            setTimeout(() => {
                setGenerating(null);
                if (onRefresh) onRefresh();
            }, 10000);
        } catch (e: any) {
            console.error(e);
            setGenerating(null);
            alert("Failed to request generation: " + (e.message || "Unknown error"));
        }
    };

    return (
        <div className="w-full max-w-4xl mx-auto bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-8 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
                    <FileText className="w-5 h-5 text-indigo-400" />
                    Project Documents
                    <button
                        onClick={() => onRefresh && onRefresh()}
                        className="ml-2 p-1 text-zinc-500 hover:text-white rounded-full hover:bg-zinc-800 transition-colors"
                        title="Refresh List"
                    >
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </h3>
                <div className="flex gap-2">
                    <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleGenerate('outline')}
                        isLoading={generating === 'outline'}
                        className="text-xs h-8 bg-zinc-800 hover:bg-zinc-700 border-zinc-700"
                    >
                        Generate Outline
                    </Button>
                    <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleGenerate('summary')}
                        isLoading={generating === 'summary'}
                        className="text-xs h-8 bg-zinc-800 hover:bg-zinc-700 border-zinc-700"
                    >
                        Generate Summary
                    </Button>
                </div>
            </div>

            {(!files || files.length === 0) && (
                <div className="text-zinc-500 text-sm italic py-4 text-center bg-zinc-950/50 rounded-lg border border-dashed border-zinc-800">
                    No documents generated yet. Use the buttons above to create them.
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {files && files.map((file) => (
                    <div key={file.name} className="flex flex-col gap-2 p-4 bg-zinc-950 rounded-lg border border-zinc-800 hover:border-zinc-700 transition-colors">
                        <div className="flex items-center gap-2 text-zinc-300">
                            {file.type.includes('Audio') ? <FileAudio className="w-4 h-4 text-purple-400" /> : <FileText className="w-4 h-4 text-emerald-400" />}
                            <span className="text-sm font-medium truncate" title={file.type}>{file.type}</span>
                        </div>
                        <div className="text-xs text-zinc-500 truncate" title={file.name}>
                            {file.name}
                        </div>
                        <Button
                            variant="secondary"
                            onClick={() => handleDownload(file.name)}
                            icon={<Download className="w-3 h-3" />}
                            className="mt-2 text-xs h-8 w-full"
                        >
                            Download
                        </Button>
                    </div>
                ))}
            </div>
        </div>
    );
};
