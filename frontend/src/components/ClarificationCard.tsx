import React, { useState, useRef, useEffect } from 'react';
import { Check, ChevronRight } from 'lucide-react';
import { cn } from '../lib/utils';

export interface ClarificationQuestion {
  id: string;
  question: string;
}

interface ClarificationCardProps {
  questions: ClarificationQuestion[];
  onComplete: (answers: Record<string, string>) => void;
}

export const ClarificationCard: React.FC<ClarificationCardProps> = ({ questions, onComplete }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const currentQuestion = questions[currentIndex];
  const isLast = currentIndex === questions.length - 1;

  useEffect(() => {
    inputRef.current?.focus();
  }, [currentIndex]);

  const advance = (value: string) => {
    const newAnswers = { ...answers, [currentQuestion.id]: value };
    setAnswers(newAnswers);
    setInputValue('');

    if (isLast) {
      onComplete(newAnswers);
    } else {
      setCurrentIndex(i => i + 1);
    }
  };

  const handleSubmit = () => {
    if (inputValue.trim()) advance(inputValue.trim());
  };

  const handleSkip = () => advance('skip');

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="mt-3 bg-surface-container-lowest border border-primary/20 rounded-2xl p-5 space-y-4 shadow-sm">
      {/* Progress dots */}
      <div className="flex items-center gap-2">
        <div className="flex gap-1.5">
          {questions.map((_, i) => (
            <div
              key={i}
              className={cn(
                'rounded-full transition-all duration-300',
                i < currentIndex
                  ? 'w-2 h-2 bg-primary'
                  : i === currentIndex
                  ? 'w-2 h-2 bg-primary/50'
                  : 'w-1.5 h-1.5 bg-outline-variant/40 mt-0.5',
              )}
            />
          ))}
        </div>
        <span className="text-[10px] font-black text-outline uppercase tracking-widest">
          Question {currentIndex + 1} of {questions.length}
        </span>
      </div>

      {/* Previously answered */}
      {currentIndex > 0 && (
        <div className="space-y-1.5 pb-1 border-b border-outline-variant/20">
          {questions.slice(0, currentIndex).map((q) => (
            <div key={q.id} className="flex items-start gap-2">
              <Check className="w-3 h-3 text-primary mt-0.5 shrink-0" />
              <div className="min-w-0">
                <span className="text-[10px] font-bold text-outline uppercase tracking-wide block truncate">
                  {q.question}
                </span>
                <span className="text-xs font-semibold text-on-surface">
                  {answers[q.id] === 'skip' ? (
                    <span className="italic text-outline">Skipped</span>
                  ) : (
                    answers[q.id]
                  )}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Current question */}
      <p className="text-sm font-semibold text-on-surface leading-relaxed">
        {currentQuestion.question}
      </p>

      {/* Input row */}
      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Type your answer…"
          className="flex-1 min-w-0 bg-surface-container-low border border-outline-variant/50 rounded-xl px-3 py-2 text-sm font-medium focus:ring-2 focus:ring-primary focus:border-transparent outline-none"
        />
        <button
          onClick={handleSubmit}
          disabled={!inputValue.trim()}
          className="flex items-center gap-1 px-4 py-2 bg-primary text-white rounded-xl text-xs font-black uppercase tracking-widest disabled:opacity-40 hover:scale-105 active:scale-95 transition-all shadow-sm shrink-0"
        >
          {isLast ? 'Submit' : 'Next'}
          {!isLast && <ChevronRight className="w-3 h-3" />}
        </button>
        <button
          onClick={handleSkip}
          className="px-3 py-2 bg-surface-container border border-outline-variant/30 rounded-xl text-xs font-black uppercase tracking-widest text-outline hover:text-on-surface hover:border-outline-variant transition-all shrink-0"
        >
          Skip
        </button>
      </div>

      {isLast && inputValue.trim() === '' && (
        <p className="text-[10px] text-outline text-center">
          Press Skip to proceed without answering, or type your answer and press Submit.
        </p>
      )}
    </div>
  );
};
