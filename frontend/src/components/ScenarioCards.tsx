import React from 'react';
import { Check, X, ChevronDown, Star, ThumbsUp, ThumbsDown } from 'lucide-react';
import { ChatChart, type ChartArtifact } from './ChatChart';

/**
 * Goal-planning scenario cards (A/B/C/D), rendered below the AI's main answer.
 *
 * Each card (from answer_node `_build_scenario_cards`) shows a title, a feasibility badge and a
 * headline number. Clicking a card expands it INLINE to reveal the key metrics, pros/cons and
 * this scenario's own charts (bank-balance trajectory, funding split, spending-cut breakdown).
 */

export interface ScenarioCard {
  tag: string;
  title: string;
  subtitle?: string;
  recommended?: boolean;
  feasible?: boolean;
  headline?: string;
  metrics?: Array<{ label: string; value: string }>;
  charts?: ChartArtifact[];
  pros?: string[];
  cons?: string[];
  bottom_line?: string;
}

const FeasibilityBadge: React.FC<{ feasible?: boolean }> = ({ feasible }) => (
  <span
    className={
      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ' +
      (feasible
        ? 'bg-emerald-100 text-emerald-700'
        : 'bg-rose-100 text-rose-700')
    }
  >
    {feasible ? <Check size={11} strokeWidth={3} /> : <X size={11} strokeWidth={3} />}
    {feasible ? 'Affordable' : 'Not affordable'}
  </span>
);

const ScenarioCardItem: React.FC<{ card: ScenarioCard }> = ({ card }) => {
  const [open, setOpen] = React.useState(false);

  return (
    <div
      className={
        'rounded-2xl border bg-surface-container-lowest overflow-hidden transition-shadow ' +
        (card.recommended ? 'border-lumio-black/70 shadow-sm' : 'border-outline-variant/40')
      }
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 p-3 text-left hover:bg-black/[0.02]"
        aria-expanded={open}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-black text-on-surface-variant">{card.tag}</span>
            <span className="font-semibold text-sm truncate">{card.title}</span>
            {card.recommended && (
              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-600">
                <Star size={11} fill="currentColor" /> Recommended
              </span>
            )}
          </div>
          {card.subtitle && (
            <p className="text-[11px] text-on-surface-variant truncate mt-0.5">{card.subtitle}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {card.headline && (
            <span className="text-sm font-bold tabular-nums">{card.headline}</span>
          )}
          <FeasibilityBadge feasible={card.feasible} />
          <ChevronDown
            size={16}
            className={'text-on-surface-variant transition-transform ' + (open ? 'rotate-180' : '')}
          />
        </div>
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-outline-variant/30 space-y-3">
          {card.bottom_line && (
            <p className="text-[12px] leading-relaxed text-on-surface font-medium">{card.bottom_line}</p>
          )}

          {Array.isArray(card.metrics) && card.metrics.length > 0 && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {card.metrics.map((m, i) => (
                <div key={i} className="flex justify-between gap-2 text-[12px]">
                  <span className="text-on-surface-variant truncate">{m.label}</span>
                  <span className="font-semibold tabular-nums shrink-0">{m.value}</span>
                </div>
              ))}
            </div>
          )}

          {(card.pros?.length || card.cons?.length) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {card.pros?.length ? (
                <div>
                  <p className="flex items-center gap-1 text-[11px] font-bold text-emerald-700 mb-1">
                    <ThumbsUp size={12} /> Pros
                  </p>
                  <ul className="space-y-1">
                    {card.pros.map((p, i) => (
                      <li key={i} className="text-[12px] text-on-surface flex gap-1.5">
                        <span className="text-emerald-600 mt-0.5">+</span>
                        <span>{p}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {card.cons?.length ? (
                <div>
                  <p className="flex items-center gap-1 text-[11px] font-bold text-rose-700 mb-1">
                    <ThumbsDown size={12} /> Cons
                  </p>
                  <ul className="space-y-1">
                    {card.cons.map((c, i) => (
                      <li key={i} className="text-[12px] text-on-surface flex gap-1.5">
                        <span className="text-rose-500 mt-0.5">−</span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}

          {Array.isArray(card.charts) &&
            card.charts.map((art, i) => <ChatChart key={i} artifact={art} />)}
        </div>
      )}
    </div>
  );
};

export const ScenarioCards: React.FC<{ scenarios: ScenarioCard[] }> = ({ scenarios }) => {
  if (!Array.isArray(scenarios) || scenarios.length === 0) return null;
  const single = scenarios.length === 1;
  return (
    <div className="mt-3 space-y-2">
      <p className="text-[10px] font-black text-on-surface-variant uppercase tracking-widest px-1">
        {single ? 'Tap for the full breakdown' : 'Your options — tap a card for the full breakdown'}
      </p>
      {scenarios.map((card) => (
        <ScenarioCardItem key={card.tag} card={card} />
      ))}
    </div>
  );
};
