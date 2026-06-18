import React, { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { APP_NAME } from '../../lib/utils';

const STEPS = [
  {
    id: 'aggregate',
    title: 'Aggregate',
    desc: 'Connect financial data across accounts, portfolios, and institutions.',
  },
  {
    id: 'analyze',
    title: 'Analyze',
    desc: 'Surface meaningful patterns and performance indicators automatically.',
  },
  {
    id: 'advise',
    title: 'Advise',
    desc: 'Receive contextual recommendations that support better financial outcomes.',
  },
] as const;

function AggregatePanel() {
  const sources = [
    { icon: 'account_balance', label: 'HDFC Savings', meta: 'Linked' },
    { icon: 'credit_card', label: 'Amex Platinum', meta: 'Synced' },
    { icon: 'trending_up', label: 'Equity Portfolio', meta: 'Live' },
    { icon: 'savings', label: 'Mutual Funds', meta: 'Connected' },
  ];
  return (
    <div className="w-full max-w-md bg-white-card rounded-2xl shadow-xl border border-lumio-line/20 p-6">
      <p className="font-label text-xs font-bold text-lumio-muted uppercase tracking-widest mb-4">
        Unified data layer
      </p>
      <div className="space-y-3">
        {sources.map((item) => (
          <div
            key={item.label}
            className="flex items-center justify-between gap-3 p-3 bg-soft-card/60 rounded-xl border border-lumio-line/10"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="material-symbols-outlined text-lumio-black text-lg">{item.icon}</span>
              <span className="text-sm font-medium truncate">{item.label}</span>
            </div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 shrink-0">
              {item.meta}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AnalyzePanel() {
  const bars = [42, 68, 55, 82, 61, 74, 48];
  return (
    <div className="w-full max-w-md bg-white-card rounded-2xl shadow-xl border border-lumio-line/20 p-6">
      <p className="font-label text-xs font-bold text-lumio-muted uppercase tracking-widest mb-4">
        Pattern detection
      </p>
      <div className="flex items-end justify-between gap-2 h-36 mb-4 px-1">
        {bars.map((h, i) => (
          <div
            key={i}
            className="flex-1 rounded-t-md bg-gradient-to-t from-[#FF416C] to-[#FF4B2B]/70"
            style={{ height: `${h}%` }}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-xl bg-soft-card/80 border border-lumio-line/10">
          <p className="text-[10px] uppercase tracking-wider text-lumio-muted mb-1">Top category</p>
          <p className="text-sm font-bold">Food &amp; Dining</p>
        </div>
        <div className="p-3 rounded-xl bg-soft-card/80 border border-lumio-line/10">
          <p className="text-[10px] uppercase tracking-wider text-lumio-muted mb-1">MoM change</p>
          <p className="text-sm font-bold text-[#FF4B2B]">+12.4%</p>
        </div>
      </div>
    </div>
  );
}

function AdvisePanel() {
  return (
    <div className="w-full max-w-md bg-white-card rounded-2xl shadow-xl border border-lumio-line/20 p-6">
      <div className="flex items-center gap-2 mb-4">
        <span className="material-symbols-outlined text-[#FF4B2B] text-lg">auto_awesome</span>
        <p className="font-label text-xs font-bold text-lumio-muted uppercase tracking-widest">
          {APP_NAME} Advisor
        </p>
      </div>
      <div className="space-y-3">
        {[
          'Raise emergency buffer to 6 months of expenses.',
          'Reduce credit utilization below 30% to lift health score.',
          'Reallocate ₹8,000/month from discretionary to savings.',
        ].map((rec) => (
          <div
            key={rec}
            className="flex gap-2 p-3 rounded-xl bg-gradient-to-r from-soft-card-2/80 to-soft-card/40 border border-lumio-line/10"
          >
            <span className="text-[#FF4B2B] text-xs mt-0.5">•</span>
            <p className="text-sm text-lumio-text/90 leading-relaxed">{rec}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

const PANELS = [AggregatePanel, AnalyzePanel, AdvisePanel];

export const FoundationScrollSection: React.FC = () => {
  const sectionRef = useRef<HTMLElement>(null);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    const onScroll = () => {
      const section = sectionRef.current;
      if (!section) return;

      const rect = section.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const scrollable = section.offsetHeight - viewportHeight;
      if (scrollable <= 0) return;

      const scrolled = Math.min(Math.max(-rect.top, 0), scrollable);
      const progress = scrolled / scrollable;
      const nextStep = Math.min(STEPS.length - 1, Math.floor(progress * STEPS.length));
      setActiveStep(nextStep);
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  const ActivePanel = PANELS[activeStep];
  const progressHeight = `${((activeStep + 1) / STEPS.length) * 100}%`;

  return (
    <section
      id="features"
      ref={sectionRef}
      className="relative"
      style={{ height: `${STEPS.length * 100}vh` }}
    >
      <div className="sticky top-0 h-screen flex items-center px-margin max-w-[1728px] mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center w-full py-16">
          <div className="bg-gradient-to-br from-soft-card-2 to-soft-card rounded-[40px] p-8 min-h-[420px] lg:min-h-[480px] flex items-center justify-center border border-lumio-line/30 overflow-hidden">
            <AnimatePresence mode="wait">
              <motion.div
                key={STEPS[activeStep].id}
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -24 }}
                transition={{ duration: 0.35, ease: 'easeOut' }}
                className="w-full flex items-center justify-center"
              >
                <ActivePanel />
              </motion.div>
            </AnimatePresence>
          </div>

          <div>
            <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight mb-10">
              The intelligent foundation
              <br />
              for your assets.
            </h2>
            <div className="relative pl-8 border-l-[3px] border-lumio-line space-y-10">
              <div
                className="absolute left-[-3px] top-0 w-[3px] bg-gradient-to-b from-[#FF416C] to-[#FF4B2B] transition-all duration-500 ease-out"
                style={{ height: progressHeight }}
              />
              {STEPS.map((item, index) => {
                const isActive = index === activeStep;
                return (
                  <motion.div
                    key={item.id}
                    animate={{ opacity: isActive ? 1 : 0.38 }}
                    transition={{ duration: 0.3 }}
                  >
                    <h3
                      className={`text-xl font-bold mb-2 transition-colors duration-300 ${
                        isActive ? 'text-lumio-text' : 'text-lumio-muted'
                      }`}
                    >
                      {item.title}
                    </h3>
                    <p className="text-lumio-muted leading-relaxed">{item.desc}</p>
                  </motion.div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
