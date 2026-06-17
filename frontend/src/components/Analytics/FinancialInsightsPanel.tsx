import React from 'react';

interface FinancialInsightsPanelProps {
  executiveSummary?: string;
  recommendations?: string[];
  loading?: boolean;
  aiLoading?: boolean;
}

export const FinancialInsightsPanel: React.FC<FinancialInsightsPanelProps> = ({
  executiveSummary,
  recommendations = [],
  loading,
  aiLoading,
}) => {
  if (loading) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 animate-pulse h-40" />
    );
  }

  if (!executiveSummary && !recommendations.length && !aiLoading) {
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
    </div>
  );
};
