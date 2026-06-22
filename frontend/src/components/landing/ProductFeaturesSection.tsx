import React from 'react';

type Feature = {
  id: string;
  icon: string;
  title: string;
  tagline: string;
  accent: string;
  Visual: React.FC<{ accent: string }>;
};

function ChatVisual({ accent }: { accent: string }) {
  return (
    <div className="mt-4 space-y-2">
      <div className="ml-auto w-[78%] rounded-xl rounded-tr-sm bg-lumio-black text-white px-2.5 py-1.5 text-[10px] font-medium">
        Can I afford this EMI?
      </div>
      <div className="flex gap-1.5 items-start">
        <span className="material-symbols-outlined text-sm shrink-0" style={{ color: accent }}>auto_awesome</span>
        <p className="text-[10px] text-lumio-muted leading-snug">Yes — 28% commitments leaves ₹18K buffer.</p>
      </div>
    </div>
  );
}

function InvestmentVisual({ accent }: { accent: string }) {
  return (
    <div className="mt-4 flex items-center gap-3">
      <div className="relative w-12 h-12 shrink-0">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx="50" cy="50" r="38" fill="none" stroke="#eee" strokeWidth="10" />
          <circle cx="50" cy="50" r="38" fill="none" stroke={accent} strokeWidth="10" strokeDasharray="95 239" />
          <circle cx="50" cy="50" r="38" fill="none" stroke="#FF4B2B" strokeWidth="10" strokeDasharray="72 239" strokeDashoffset="-95" />
        </svg>
      </div>
      <div className="text-[10px] font-semibold space-y-1">
        <p className="text-lumio-muted">MF · FD · Liquid</p>
        <p className="text-sm font-bold text-lumio-text">₹19.1L</p>
      </div>
    </div>
  );
}

function ForecastVisual({ accent }: { accent: string }) {
  return (
    <div className="mt-4">
      <svg viewBox="0 0 200 36" className="w-full h-9" preserveAspectRatio="none">
        <path d="M0,28 L40,22 L80,26 L120,14 L160,18 L200,8" fill="none" stroke={accent} strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      <p className="text-sm font-bold mt-1">₹62,400 <span className="text-[10px] font-normal text-lumio-muted">next month</span></p>
    </div>
  );
}

function GoalsVisual({ accent }: { accent: string }) {
  return (
    <div className="mt-4 space-y-2">
      {[
        { label: 'Emergency fund', pct: 78 },
        { label: 'Europe trip', pct: 42 },
      ].map((g) => (
        <div key={g.label}>
          <div className="flex justify-between text-[9px] mb-1">
            <span className="text-lumio-muted">{g.label}</span>
            <span className="font-bold">{g.pct}%</span>
          </div>
          <div className="h-1 bg-lumio-line/25 rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${g.pct}%`, background: accent }} />
          </div>
        </div>
      ))}
    </div>
  );
}

const FEATURES: Feature[] = [
  {
    id: 'ai-chat',
    icon: 'smart_toy',
    title: 'AI Assistant',
    tagline: 'Ask anything — answers use your live balances and history.',
    accent: '#FF416C',
    Visual: ChatVisual,
  },
  {
    id: 'forecast',
    icon: 'query_stats',
    title: 'Spend Prediction',
    tagline: 'Prophet-powered forecast for next month\'s expenses.',
    accent: '#FF4B2B',
    Visual: ForecastVisual,
  },
  {
    id: 'investments',
    icon: 'trending_up',
    title: 'Investment Tracking',
    tagline: 'Mutual funds, FDs, and liquid holdings in one view.',
    accent: '#1a1a1a',
    Visual: InvestmentVisual,
  },
  {
    id: 'goals',
    icon: 'flag',
    title: 'Goals & Budgets',
    tagline: 'Track savings targets and stay within limits.',
    accent: '#6366F1',
    Visual: GoalsVisual,
  },
];

export const ProductFeaturesSection: React.FC = () => {
  return (
    <section id="features" className="py-20 md:py-28 px-margin max-w-[1080px] mx-auto">
      <div className="text-center max-w-2xl mx-auto mb-12 md:mb-16">
        <p className="text-[10px] font-bold uppercase tracking-[0.25em] text-lumio-muted mb-3">Platform</p>
        <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight mb-4">
          Everything you need to decide with confidence
        </h2>
        <p className="text-sm text-lumio-muted leading-relaxed">
          AI guidance, forecasts, investments, and goals — in one place.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-6">
        {FEATURES.map((feature) => (
          <article
            key={feature.id}
            className="rounded-[24px] border border-lumio-line/15 bg-white/80 p-5 md:p-6 flex flex-col hover:shadow-md hover:border-lumio-line/25 transition-all duration-300"
          >
            <div className="flex items-center gap-2.5 mb-2">
              <span
                className="material-symbols-outlined text-xl"
                style={{ color: feature.accent }}
              >
                {feature.icon}
              </span>
              <h3 className="font-display text-base md:text-lg font-bold tracking-tight">{feature.title}</h3>
            </div>
            <p className="text-xs text-lumio-muted leading-relaxed flex-1">{feature.tagline}</p>
            <feature.Visual accent={feature.accent} />
          </article>
        ))}
      </div>
    </section>
  );
};
