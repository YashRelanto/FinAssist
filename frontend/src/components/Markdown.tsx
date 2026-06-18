import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Renders assistant message text as GitHub-flavoured markdown, styled to match the
 * FinAssist design system. Used for AI advisory responses (goal plans, analysis, etc.)
 * which arrive as markdown with headings, bold, bullet lists and tables.
 */
export const Markdown: React.FC<{ children: string }> = ({ children }) => {
  return (
    <div className="text-sm text-on-surface leading-relaxed space-y-3">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-base font-black text-on-surface mt-2 mb-1 tracking-tight">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm font-black text-on-surface mt-4 mb-1.5 pb-1 border-b border-outline-variant/30 tracking-tight">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-bold text-on-surface mt-3 mb-1">{children}</h3>
          ),
          p: ({ children }) => <p className="text-sm leading-relaxed">{children}</p>,
          strong: ({ children }) => <strong className="font-bold text-on-surface">{children}</strong>,
          em: ({ children }) => <em className="italic text-on-surface-variant">{children}</em>,
          ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 marker:text-primary">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 marker:text-primary marker:font-bold">{children}</ol>,
          li: ({ children }) => <li className="text-sm leading-relaxed pl-0.5">{children}</li>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer"
               className="text-primary font-semibold underline underline-offset-2 hover:opacity-80">
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-primary/40 pl-3 italic text-on-surface-variant">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="border-outline-variant/30 my-3" />,
          code: ({ className, children }) => {
            const isBlock = (className || '').includes('language-');
            if (isBlock) {
              return (
                <code className="block bg-surface-container-low rounded-lg p-3 text-xs font-mono overflow-x-auto text-on-surface">
                  {children}
                </code>
              );
            }
            return (
              <code className="bg-surface-container-low rounded px-1.5 py-0.5 text-[0.8em] font-mono text-primary">
                {children}
              </code>
            );
          },
          // Tables (GFM) — used by the goal-plan scenario comparison
          table: ({ children }) => (
            <div className="overflow-x-auto my-2 rounded-xl border border-outline-variant/30">
              <table className="w-full text-xs border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-surface-container-low">{children}</thead>,
          th: ({ children }) => (
            <th className="text-left font-black text-on-surface-variant uppercase tracking-wide px-3 py-2 border-b border-outline-variant/30 whitespace-nowrap">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 border-b border-outline-variant/10 text-on-surface whitespace-nowrap">
              {children}
            </td>
          ),
          tr: ({ children }) => <tr className="even:bg-surface-container-lowest/50">{children}</tr>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
};
