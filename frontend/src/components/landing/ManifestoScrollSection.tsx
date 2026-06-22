import React, { useEffect, useRef, useState } from 'react';
import { APP_NAME } from '../../lib/utils';

const MANIFESTO = `As financial data expands across your life, the need for a singular source of truth has never been more critical. ${APP_NAME} unifies your strategy.`;
const [MANIFESTO_BEFORE, MANIFESTO_AFTER] = MANIFESTO.split(APP_NAME);

function clamp01(v: number) {
  return Math.min(1, Math.max(0, v));
}

function smoothstep(t: number) {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
}

function slideProgress(rect: DOMRect, viewportHeight: number) {
  const enterStart = viewportHeight * 0.9;
  const enterEnd = viewportHeight * 0.42;
  return smoothstep((enterStart - rect.top) / (enterStart - enterEnd));
}

export const ManifestoScrollSection: React.FC = () => {
  const sectionRef = useRef<HTMLElement>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const update = () => {
      const el = sectionRef.current;
      if (!el) return;
      setProgress(slideProgress(el.getBoundingClientRect(), window.innerHeight));
    };

    update();
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, []);

  const translateY = (1 - progress) * 64;
  const opacity = 0.12 + progress * 0.88;

  return (
    <section
      id="manifesto"
      ref={sectionRef}
      className="relative py-28 md:py-36 px-margin"
    >
      <div className="max-w-[920px] mx-auto text-center">
        <p
          className="font-display text-[clamp(1.75rem,4.5vw,3.25rem)] leading-[1.18] tracking-tight text-balance will-change-[transform,opacity]"
          style={{
            opacity,
            transform: `translate3d(0, ${translateY}px, 0)`,
          }}
        >
          <span className="font-light text-lumio-text">{MANIFESTO_BEFORE}</span>
          <span className="font-semibold bg-gradient-to-r from-[#FF416C] to-[#FF4B2B] bg-clip-text text-transparent">
            {APP_NAME}
          </span>
          <span className="font-light text-lumio-text">{MANIFESTO_AFTER}</span>
        </p>
      </div>
    </section>
  );
};
