import React from 'react';
import { APP_NAME } from '../../lib/utils';

const EXAMPLE_PROMPTS = [
  'Can I afford a ₹3L car loan?',
  'Why did my health score drop?',
  'How much should I save for tax?',
];

export function AiPromptChip({ prompt }: { prompt: string }) {
  return (
    <div className="flex items-center justify-center gap-2 px-4 py-2 rounded-full bg-white/70 border border-lumio-line/15 max-w-[280px] mx-auto">
      <span className="material-symbols-outlined text-base text-[#FF4B2B] shrink-0">auto_awesome</span>
      <p className="text-[11px] text-lumio-text/80 truncate">{prompt}</p>
    </div>
  );
}

export const AIAssistantHighlight: React.FC = () => {
  return (
    <section id="assistant" className="py-24 md:py-32 px-margin">
      <div className="max-w-[640px] mx-auto text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gradient-to-r from-[#FF416C]/10 to-[#FF4B2B]/10 border border-[#FF4B2B]/20 mb-6">
          <span className="material-symbols-outlined text-lg text-[#FF4B2B]">auto_awesome</span>
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#FF4B2B]">AI Assistant</span>
        </div>

        <h2 className="font-display text-3xl md:text-5xl font-bold tracking-tight mb-4">
          Ask anything about your money.
        </h2>
        <p className="text-sm text-lumio-muted mb-12">
          Live balances, goals, and spending — answered in plain language.
        </p>

        <div className="rounded-[28px] border border-lumio-line/20 bg-gradient-to-b from-white to-soft-card/40 p-6 md:p-8 text-left shadow-lg space-y-4">
          <div className="flex justify-end">
            <div className="rounded-2xl rounded-tr-md bg-lumio-black text-white px-4 py-2.5 max-w-[85%]">
              <p className="text-sm font-medium">{EXAMPLE_PROMPTS[0]}</p>
            </div>
          </div>
          <div className="flex gap-3 items-start">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#FF416C] to-[#FF4B2B] flex items-center justify-center shrink-0">
              <span className="material-symbols-outlined text-white text-sm">smart_toy</span>
            </div>
            <div className="rounded-2xl rounded-tl-md bg-white border border-lumio-line/15 px-4 py-3 flex-1">
              <p className="text-sm text-lumio-text leading-relaxed">
                With ₹18K monthly buffer after commitments, a ₹3L loan at 9% fits — but it would raise
                monthly commitments to 34%.
              </p>
              <p className="text-[10px] uppercase tracking-wider text-lumio-muted mt-3">
                {APP_NAME} · using your profile &amp; transactions
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap justify-center gap-2 mt-6">
          {EXAMPLE_PROMPTS.map((prompt) => (
            <span
              key={prompt}
              className="text-[10px] text-lumio-muted px-3 py-1.5 rounded-full border border-lumio-line/20 bg-white/60"
            >
              {prompt}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
};
