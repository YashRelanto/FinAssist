import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '../../lib/utils';

interface CategoryAnalysisCard {
  category: string;
  headline: string;
  analysis: string;
  suggestion: string;
}

interface FinancialInsightsPanelProps {
  executiveSummary?: string;
  recommendations?: string[];
  categoryAnalysis?: CategoryAnalysisCard[];
  loading?: boolean;
  aiLoading?: boolean;
}

export const FinancialInsightsPanel: React.FC<FinancialInsightsPanelProps> = ({
  executiveSummary,
  recommendations = [],
  categoryAnalysis = [],
  loading,
  aiLoading,
}) => {
  const [openCat, setOpenCat] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 animate-pulse h-40" />
    );
  }

  if (!executiveSummary && !recommendations.length && !categoryAnalysis.length && !aiLoading) {
    return null;
  }

  return (
    <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 space-y-6">
      <div className="flex items-center gap-2">
        <h3 className="text-lg font-black tracking-tight">AI Insights</h3>
        {aiLoading && (
          <span className="inline-block w-3.5 h-3.5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        )}
      </div>

      {executiveSummary && (
        <p className="text-sm font-medium text-on-surface/90 leading-relaxed">{executiveSummary}</p>
      )}

      {recommendations.length > 0 && (
        <div>
          <p className="text-[10px] font-black text-outline uppercase tracking-widest mb-3">
            Recommendations
          </p>
          <ul className="space-y-2">
            {recommendations.map((r, i) => (
              <li key={i} className="text-xs font-medium text-on-surface/80 flex gap-2">
                <span className="text-primary">•</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {categoryAnalysis.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] font-black text-outline uppercase tracking-widest mb-3">
            Category Deep Dive
          </p>
          {categoryAnalysis.map((c) => {
            const isOpen = openCat === c.category;
            return (
              <div key={c.category} className="border border-outline-variant/20 rounded-xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setOpenCat(isOpen ? null : c.category)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-surface-container-low/50"
                >
                  <span className="text-xs font-black">{c.headline}</span>
                  <ChevronDown
                    className={cn('w-4 h-4 text-outline transition-transform', isOpen && 'rotate-180')}
                  />
                </button>
                {isOpen && (
                  <div className="px-4 pb-3 space-y-2 text-xs text-on-surface/80">
                    <p>{c.analysis}</p>
                    <p className="text-primary font-medium">{c.suggestion}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
