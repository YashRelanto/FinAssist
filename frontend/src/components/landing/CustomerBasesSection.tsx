import React, { useEffect, useRef, useState } from 'react';
import { AiPromptChip } from './AIAssistantHighlight';

type CustomerBase = {
  id: string;
  title: string;
  hint: string;
  Graphic: React.FC<{ uid: string; accent: string }>;
  glow: string;
  accent: string;
};

function HealthRing({ uid, score, accent }: { uid: string; score: number; accent: string }) {
  const offset = 138 - (score / 100) * 138;
  return (
    <div className="relative w-32 h-32 md:w-36 md:h-36">
      <svg viewBox="0 0 56 56" className="w-full h-full -rotate-90">
        <circle cx="28" cy="28" r="22" fill="none" stroke="#f0f0f0" strokeWidth="4" />
        <circle
          cx="28"
          cy="28"
          r="22"
          fill="none"
          stroke={`url(#${uid}-ring)`}
          strokeWidth="4"
          strokeDasharray="138"
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
        <defs>
          <linearGradient id={`${uid}-ring`} x1="0" y1="0" x2="1" y2="1">
            <stop stopColor={accent} />
            <stop offset="1" stopColor="#FF4B2B" />
          </linearGradient>
        </defs>
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-3xl font-display font-bold">{score}</span>
    </div>
  );
}

function YoungProfessionalGraphic({ uid, accent }: { uid: string; accent: string }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-8 p-8 md:p-10">
      <HealthRing uid={uid} score={72} accent={accent} />
      <div className="flex items-center gap-12 text-center">
        <div>
          <p className="text-2xl font-display font-bold">₹82K</p>
          <p className="text-[10px] uppercase tracking-widest text-lumio-muted mt-1">Income</p>
        </div>
        <div className="w-px h-10 bg-lumio-line/30" />
        <div>
          <p className="text-2xl font-display font-bold">28%</p>
          <p className="text-[10px] uppercase tracking-widest text-lumio-muted mt-1">Commitments</p>
        </div>
      </div>
      <AiPromptChip prompt="Can I afford a weekend trip?" />
    </div>
  );
}

function FamilyGraphic({ uid, accent }: { uid: string; accent: string }) {
  void uid;
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-10 p-8 md:p-10">
      <div className="w-full max-w-[240px]">
        <div className="flex items-end justify-between mb-3">
          <span className="material-symbols-outlined text-3xl" style={{ color: accent }}>school</span>
          <p className="text-3xl font-display font-bold">64%</p>
        </div>
        <div className="h-2 bg-lumio-line/20 rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: '64%', background: accent }} />
        </div>
        <p className="text-[10px] uppercase tracking-widest text-lumio-muted mt-3 text-center">School fund</p>
      </div>
      <p className="text-2xl font-display font-bold">₹1.2L <span className="text-base font-normal text-lumio-muted">/ mo household</span></p>
      <AiPromptChip prompt="Are we on track for school fees?" />
    </div>
  );
}

function FreelancerGraphic({ uid, accent }: { uid: string; accent: string }) {
  void uid;
  const bars = [40, 75, 30, 90, 50, 70, 45, 85];
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-10 p-8 md:p-10">
      <div className="flex items-end justify-center gap-2 h-28 w-full max-w-[260px]">
        {bars.map((h, i) => (
          <div
            key={i}
            className="flex-1 rounded-t-full opacity-80"
            style={{ height: `${h}%`, background: accent }}
          />
        ))}
      </div>
      <div className="flex items-center gap-12 text-center">
        <div>
          <p className="text-2xl font-display font-bold">₹39K</p>
          <p className="text-[10px] uppercase tracking-widest text-lumio-muted mt-1">Survival</p>
        </div>
        <div className="w-px h-10 bg-lumio-line/30" />
        <div>
          <p className="text-2xl font-display font-bold text-lumio-muted">₹61K</p>
          <p className="text-[10px] uppercase tracking-widest text-lumio-muted mt-1">Lifestyle</p>
        </div>
      </div>
      <AiPromptChip prompt="What's my runway this month?" />
    </div>
  );
}

function InvestorGraphic({ uid, accent }: { uid: string; accent: string }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-8 p-8 md:p-10">
      <div className="relative w-32 h-32 md:w-36 md:h-36">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx="50" cy="50" r="38" fill="none" stroke="#f0f0f0" strokeWidth="10" />
          <circle cx="50" cy="50" r="38" fill="none" stroke="#FF4B2B" strokeWidth="10" strokeDasharray="95 239" />
          <circle cx="50" cy="50" r="38" fill="none" stroke={accent} strokeWidth="10" strokeDasharray="72 239" strokeDashoffset="-95" />
          <circle cx="50" cy="50" r="38" fill="none" stroke="#1a1a1a" strokeWidth="10" strokeDasharray="48 239" strokeDashoffset="-167" />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-xl font-display font-bold">₹19L</span>
      </div>
      <div className="w-full max-w-[220px]">
        <svg viewBox="0 0 200 40" className="w-full h-8" preserveAspectRatio="none">
          <path
            d="M0,32 L50,24 L100,28 L150,12 L200,8"
            fill="none"
            stroke={accent}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="text-[10px] uppercase tracking-widest text-lumio-muted mt-3 text-center">₹62K forecast · next month</p>
      </div>
      <AiPromptChip prompt="Should I prepay my home loan?" />
    </div>
  );
}

const CUSTOMER_BASES: CustomerBase[] = [
  {
    id: 'professionals',
    title: 'Young Professionals',
    hint: 'Salary · Rent · Health score · AI',
    glow: 'from-[#FF416C]/12 to-white',
    accent: '#FF416C',
    Graphic: YoungProfessionalGraphic,
  },
  {
    id: 'families',
    title: 'Growing Families',
    hint: 'Goals · Household · AI',
    glow: 'from-[#6366F1]/10 to-white',
    accent: '#6366F1',
    Graphic: FamilyGraphic,
  },
  {
    id: 'freelancers',
    title: 'Freelancers',
    hint: 'Burn rate · Forecast · AI',
    glow: 'from-emerald-500/10 to-white',
    accent: '#059669',
    Graphic: FreelancerGraphic,
  },
  {
    id: 'investors',
    title: 'Investors',
    hint: 'Portfolio · Planner · AI',
    glow: 'from-lumio-black/5 to-white',
    accent: '#1a1a1a',
    Graphic: InvestorGraphic,
  },
];

function clamp01(v: number) {
  return Math.min(1, Math.max(0, v));
}

function smoothstep(t: number) {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
}

function cardTransform(offset: number): React.CSSProperties {
  const dist = Math.abs(offset);
  const focus = smoothstep(1 - dist);
  const rotateY = offset * -42;
  const translateX = offset * 55;
  const translateZ = -280 + focus * 260;
  const scale = 0.82 + focus * 0.18;
  const opacity = dist > 1.2 ? 0 : 0.15 + focus * 0.85;

  return {
    opacity,
    transform: `translateX(${translateX}%) translateZ(${translateZ}px) rotateY(${rotateY}deg) scale(${scale})`,
    zIndex: Math.round(100 - dist * 10),
    pointerEvents: dist < 0.35 ? 'auto' : 'none',
  };
}

export const CustomerBasesSection: React.FC = () => {
  const sectionRef = useRef<HTMLElement>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const onScroll = () => {
      const section = sectionRef.current;
      if (!section) return;

      const rect = section.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const scrollable = section.offsetHeight - viewportHeight;
      if (scrollable <= 0) return;

      const scrolled = Math.min(Math.max(-rect.top, 0), scrollable);
      setProgress(scrolled / scrollable);
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  const activeFloat = progress * (CUSTOMER_BASES.length - 1);

  return (
    <section
      ref={sectionRef}
      className="relative"
      style={{ height: `${CUSTOMER_BASES.length * 70 + 40}vh` }}
    >
      <div className="sticky top-0 h-screen flex flex-col items-center justify-center px-margin overflow-hidden">
        <h2 className="font-display text-3xl md:text-4xl font-bold text-center mb-8 md:mb-10 shrink-0">
          Built for every team.
        </h2>

        <div
          className="relative w-full max-w-[480px] md:max-w-[520px] h-[min(56vh,520px)]"
          style={{ perspective: '1600px', perspectiveOrigin: '50% 42%' }}
        >
          {CUSTOMER_BASES.map((base, index) => {
            const offset = index - activeFloat;
            const isFocused = Math.abs(offset) < 0.45;

            return (
              <article
                key={base.id}
                className="absolute inset-0 will-change-transform"
                style={{
                  ...cardTransform(offset),
                  transformStyle: 'preserve-3d',
                  backfaceVisibility: 'hidden',
                }}
              >
                <div
                  className={`h-full rounded-[36px] border border-lumio-line/15 overflow-hidden bg-gradient-to-br ${base.glow} shadow-lg flex flex-col`}
                >
                  <div className="px-8 pt-8 pb-2 shrink-0 text-center">
                    <h3
                      className={`font-display font-bold tracking-tight transition-colors duration-300 ${
                        isFocused ? 'text-lumio-text' : 'text-lumio-muted'
                      } text-[clamp(1.875rem,5.5vw,2.75rem)]`}
                    >
                      {base.title}
                    </h3>
                    <p className="text-[11px] uppercase tracking-[0.2em] text-lumio-muted mt-3">{base.hint}</p>
                  </div>

                  <div className="flex-1 min-h-0">
                    <base.Graphic uid={base.id} accent={base.accent} />
                  </div>
                </div>
              </article>
            );
          })}
        </div>

        <div className="flex gap-2 mt-8 shrink-0" aria-hidden>
          {CUSTOMER_BASES.map((base, index) => {
            const dist = Math.abs(index - activeFloat);
            return (
              <span
                key={base.id}
                className="h-1.5 rounded-full bg-lumio-line/30 transition-all duration-300"
                style={{
                  width: dist < 0.5 ? 28 : 8,
                  opacity: dist < 0.5 ? 1 : 0.45,
                  background: dist < 0.5 ? 'linear-gradient(90deg,#FF416C,#FF4B2B)' : undefined,
                }}
              />
            );
          })}
        </div>
      </div>
    </section>
  );
};
