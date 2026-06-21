import React, { useEffect, useRef, useState } from 'react';
import { APP_NAME } from '../../lib/utils';

const MANIFESTO = `As financial data expands across your life, the need for a singular source of truth has never been more critical. ${APP_NAME} unifies your strategy.`;

const WORDS = MANIFESTO.split(/\s+/);
const ACCENT_START = WORDS.findIndex((w) => w.startsWith('FinAssist'));

function clamp01(v: number) {
  return Math.min(1, Math.max(0, v));
}

function smoothstep(t: number) {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
}

function wordReveal(progress: number, index: number, total: number) {
  // Overlapping windows so words flow in continuously — no hard step boundaries.
  const spread = 0.72;
  const overlap = 0.55;
  const start = (index / total) * spread;
  const t = smoothstep((progress - start) / overlap);
  return t;
}

export const ManifestoScrollSection: React.FC = () => {
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

  const blockEase = smoothstep(progress);
  const blockRotateX = 18 - blockEase * 20;
  const blockRotateY = -6 + progress * 12;
  const blockTranslateZ = -140 + blockEase * 160;
  const blockTranslateY = 48 - blockEase * 56;
  const blockScale = 0.9 + blockEase * 0.1;
  const glowOpacity = 0.08 + blockEase * 0.18;

  return (
    <section id="manifesto" ref={sectionRef} className="relative" style={{ height: '220vh' }}>
      <div className="sticky top-0 h-screen flex items-center justify-center px-margin overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center"
          aria-hidden
        >
          <div
            className="w-[min(90vw,720px)] h-[min(90vw,720px)] rounded-full blur-3xl bg-gradient-to-br from-[#FF416C]/30 to-[#FF4B2B]/20"
            style={{ opacity: glowOpacity, transform: `translateZ(-200px) scale(${1 + progress * 0.15})` }}
          />
        </div>

        <div
          className="relative max-w-[920px] mx-auto text-center"
          style={{ perspective: '1400px', perspectiveOrigin: '50% 45%' }}
        >
          <p
            className="font-display text-[clamp(1.75rem,4.5vw,3.25rem)] leading-[1.18] tracking-tight text-balance"
            style={{
              transformStyle: 'preserve-3d',
              transform: `rotateX(${blockRotateX}deg) rotateY(${blockRotateY}deg) translateY(${blockTranslateY}px) translateZ(${blockTranslateZ}px) scale(${blockScale})`,
            }}
          >
            {WORDS.map((word, index) => {
              const t = wordReveal(progress, index, WORDS.length);
              const isAccent = index >= ACCENT_START;
              const rotateX = (1 - t) * 32;
              const translateZ = (1 - t) * -90;
              const translateY = (1 - t) * 18;
              const opacity = 0.1 + t * 0.9;
              const blur = (1 - t) * 3;

              return (
                <span
                  key={`${word}-${index}`}
                  className={`inline-block mr-[0.28em] will-change-transform ${
                    isAccent ? 'font-semibold bg-gradient-to-r from-[#FF416C] to-[#FF4B2B] bg-clip-text text-transparent' : 'font-light text-lumio-text'
                  }`}
                  style={{
                    opacity,
                    filter: blur > 0.1 ? `blur(${blur}px)` : undefined,
                    transform: `rotateX(${rotateX}deg) translateZ(${translateZ}px) translateY(${translateY}px)`,
                    backfaceVisibility: 'hidden',
                  }}
                >
                  {word}
                </span>
              );
            })}
          </p>
        </div>
      </div>
    </section>
  );
};
