
import React, { useEffect, useRef } from 'react';
import { LogEntry } from '../types';
import { Terminal, X } from 'lucide-react';

interface LogConsoleProps {
  logs: LogEntry[];
  isOpen: boolean;
  onClose: () => void;
}

export const LogConsole: React.FC<LogConsoleProps> = ({ logs, isOpen, onClose }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-0 right-0 w-full md:w-96 h-64 bg-zinc-950 border-t md:border-l border-zinc-800 shadow-2xl z-50 flex flex-col font-mono text-xs">
      <div className="flex items-center justify-between p-2 bg-zinc-900 border-b border-zinc-800">
        <div className="flex items-center text-zinc-400">
          <Terminal className="w-3 h-3 mr-2" />
          <span>Processing Logs</span>
        </div>
        <button onClick={onClose} className="text-zinc-500 hover:text-white">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {logs.length === 0 && <div className="text-zinc-600 italic">Ready to process...</div>}
        {logs.map((log, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-zinc-600 shrink-0">[{log.time}]</span>
            <span className={`${
              log.type === 'error' ? 'text-red-400' : 
              log.type === 'success' ? 'text-emerald-400' : 'text-zinc-300'
            }`}>
              {log.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};
