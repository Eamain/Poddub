import React from 'react';
import { AppState } from '../types';

interface StepIndicatorProps {
  currentStep: AppState;
}

export const StepIndicator: React.FC<StepIndicatorProps> = ({ currentStep }) => {
  const steps = [
    { id: AppState.IDLE, label: 'Upload' },
    { id: AppState.ANALYZING, label: 'Transcribe & Translate' },
    { id: AppState.REVIEW, label: 'Review Script' },
    { id: AppState.GENERATING, label: 'AI Dubbing' },
    { id: AppState.PLAYBACK, label: 'Play' },
  ];

  // Helper to determine step status
  const getStatus = (stepId: AppState, currentIndex: number, stepIndex: number) => {
    if (stepId === AppState.ERROR) return 'inactive'; // Handle error separately if needed
    if (stepIndex < currentIndex) return 'completed';
    if (stepIndex === currentIndex) return 'active';
    return 'inactive';
  };

  const currentIndex = steps.findIndex(s => s.id === currentStep);

  return (
    <div className="w-full py-6">
      <div className="flex items-center justify-between relative">
        <div className="absolute left-0 top-1/2 transform -translate-y-1/2 w-full h-1 bg-zinc-800 -z-10" />
        {steps.map((step, index) => {
          const status = getStatus(currentStep, currentIndex, index);

          let circleClass = "bg-zinc-800 border-zinc-600 text-zinc-500";
          if (status === 'active') circleClass = "bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-500/50 scale-110";
          if (status === 'completed') circleClass = "bg-green-500 border-green-500 text-white";

          return (
            <div key={step.id} className="flex flex-col items-center group">
              <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-xs font-bold transition-all duration-300 ${circleClass}`}>
                {status === 'completed' ? '✓' : index + 1}
              </div>
              <span className={`mt-2 text-xs font-medium transition-colors ${status === 'active' ? 'text-blue-400' : 'text-zinc-500'}`}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
