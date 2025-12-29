
import React, { useRef, useState, useEffect } from 'react';
import { Upload, FileAudio, Youtube, Link, Download, AlertCircle, ExternalLink, FileJson, FolderInput, RotateCw } from 'lucide-react';
import { Button } from './Button';
import { extractYoutubeAudio } from '../services/youtubeService';
import { ProjectData } from '../types';

interface AudioUploaderProps {
  onFileSelect: (file: File) => void;
  onProjectImport: (data: ProjectData) => void;
  isProcessing: boolean;
}

export const AudioUploader: React.FC<AudioUploaderProps> = ({ onFileSelect, onProjectImport, isProcessing }) => {
  const [activeTab, setActiveTab] = useState<'upload' | 'import'>('upload');
  const [dragActive, setDragActive] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualDownloadUrl, setManualDownloadUrl] = useState<string | null>(null);
  const [hasSavedSession, setHasSavedSession] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const jsonInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const saved = localStorage.getItem('poddub_autosave');
    if (saved) {
      setHasSavedSession(true);
    }
  }, []);

  const handleRestoreSession = () => {
    try {
      const saved = localStorage.getItem('poddub_autosave');
      if (saved) {
        const data = JSON.parse(saved);
        if (data.segments && data.segments.length > 0) {
          onProjectImport(data);
        }
      }
    } catch (e) {
      console.error("Failed to restore session", e);
      localStorage.removeItem('poddub_autosave');
      setHasSavedSession(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (activeTab === 'import' && file.name.endsWith('.json')) {
        handleJsonFile(file);
      } else if (activeTab === 'upload') {
        validateAndPass(file);
      }
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      validateAndPass(e.target.files[0]);
    }
  };

  const handleJsonChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleJsonFile(e.target.files[0]);
    }
  };

  const validateAndPass = (file: File) => {
    if (!file.type.startsWith('audio/') && !file.type.startsWith('video/')) {
      alert("Please upload an audio or video file.");
      return;
    }
    onFileSelect(file);
  };

  const handleJsonFile = (file: File) => {
    // Treat JSON import as a file upload so backend handles job creation
    onFileSelect(file);
  };

  const onButtonClick = () => {
    inputRef.current?.click();
  };

  const onJsonButtonClick = () => {
    jsonInputRef.current?.click();
  };

  const handleYoutubeExtract = async () => {
    if (!youtubeUrl.trim()) return;

    setIsExtracting(true);
    setError(null);
    setManualDownloadUrl(null);

    try {
      const file = await extractYoutubeAudio(youtubeUrl);
      onFileSelect(file);
    } catch (e: any) {
      console.error("Extraction error:", e);

      // If we got a URL but failed to download file
      if (e.name === 'AudioDownloadError' && e.downloadUrl) {
        setManualDownloadUrl(e.downloadUrl);
        setError("Browser blocked the download. Click the button below to download manually.");
      } else {
        // If we failed to even get the URL
        setError("Unable to extract audio automatically.");
      }
    } finally {
      setIsExtracting(false);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <div className="flex justify-center space-x-2 mb-6">
        <button
          onClick={() => setActiveTab('upload')}
          className={`flex items-center px-4 py-2 rounded-full text-sm font-medium transition-all ${activeTab === 'upload'
            ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20'
            : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
            }`}
        >
          <Upload className="w-4 h-4 mr-2" />
          Upload
        </button>
        <button
          onClick={() => setActiveTab('import')}
          className={`flex items-center px-4 py-2 rounded-full text-sm font-medium transition-all ${activeTab === 'import'
            ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/20'
            : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
            }`}
        >
          <FolderInput className="w-4 h-4 mr-2" />
          Import Project
        </button>
      </div>

      {/* Auto-Save Restore Alert */}
      {hasSavedSession && activeTab !== 'import' && !isProcessing && (
        <div className="bg-blue-900/20 border border-blue-800 p-4 rounded-lg flex items-center justify-between animate-in fade-in slide-in-from-top-2">
          <div className="flex items-center text-blue-200 text-sm">
            <RotateCw className="w-4 h-4 mr-2" />
            <span>Found a previous interrupted session.</span>
          </div>
          <Button variant="ghost" onClick={handleRestoreSession} className="text-xs h-8 bg-blue-900/40 hover:bg-blue-800">
            Restore Script
          </Button>
        </div>
      )}

      {activeTab === 'upload' && (
        <div
          className={`relative border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300 ${dragActive ? "border-blue-500 bg-blue-500/10" : "border-zinc-700 hover:border-zinc-600 bg-zinc-900/50"
            }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept="audio/*,video/*"
            onChange={handleChange}
            disabled={isProcessing}
          />

          <div className="flex flex-col items-center space-y-4">
            <div className="w-16 h-16 bg-zinc-800 rounded-full flex items-center justify-center">
              <FileAudio className="w-8 h-8 text-zinc-400" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-zinc-100">Upload Podcast Audio</h3>
              <p className="text-zinc-500 mt-2">Drag & drop or click to browse</p>
            </div>
            <Button onClick={onButtonClick} disabled={isProcessing}>
              Select Audio File
            </Button>
          </div>
        </div>
      )}

      {activeTab === 'import' && (
        <div
          className={`relative border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300 ${dragActive ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-700 hover:border-zinc-600 bg-zinc-900/50"
            }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            ref={jsonInputRef}
            type="file"
            className="hidden"
            accept=".json"
            onChange={handleJsonChange}
            disabled={isProcessing}
          />

          <div className="flex flex-col items-center space-y-4">
            <div className="w-16 h-16 bg-zinc-800 rounded-full flex items-center justify-center">
              <FileJson className="w-8 h-8 text-emerald-400" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-zinc-100">Import Project File</h3>
              <p className="text-zinc-500 mt-2">Upload a previously saved .json script</p>
            </div>
            <Button onClick={onJsonButtonClick} disabled={isProcessing} className="bg-emerald-600 hover:bg-emerald-700">
              Select JSON File
            </Button>
          </div>
        </div>
      )}

    </div>
  );
};
