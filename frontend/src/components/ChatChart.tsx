import React from 'react';
import {
  ResponsiveContainer,
  LineChart, Line,
  BarChart, Bar,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import { formatCurrency } from '../lib/utils';

/**
 * Renders a single visualization artifact returned by the AI assistant backend.
 *
 * Artifact shape (from answer_node):
 *   { type: "chart", chart_type: "line"|"bar"|"pie", title, x_field, y_field, data: [...] }
 *
 * The data keys are given by x_field / y_field, so the same component handles
 * trend (line), comparison/breakdown (bar/pie) and portfolio allocation (pie).
 */

export interface ChartArtifact {
  type: string;
  chart_type: 'line' | 'bar' | 'pie' | string;
  title?: string;
  x_field: string;
  y_field: string;
  data: Array<Record<string, any>>;
}

const COLORS = [
  '#4D96FF', '#FF6B6B', '#6BCB77', '#FFD93D', '#A55EEF',
  '#48DBFB', '#FF9F43', '#10AC84', '#546E7A', '#FF4757',
];

const AXIS_STYLE = { fontSize: 10, fontWeight: 700, fill: 'var(--color-outline, #8a8a8a)' } as const;

export const ChatChart: React.FC<{ artifact: ChartArtifact }> = ({ artifact }) => {
  const { chart_type, title, x_field, y_field, data } = artifact || ({} as ChartArtifact);

  if (!data || data.length === 0 || !x_field || !y_field) return null;

  // Percentages (portfolio share) use `value`; monetary series use `amount`.
  const isPercent = y_field === 'value';
  const fmt = (v: number) => (isPercent ? `${Number(v).toFixed(1)}%` : formatCurrency(Number(v)));

  const tooltip = (
    <Tooltip
      formatter={(v: any, name: any) => [fmt(v as number), name]}
      contentStyle={{
        borderRadius: 12,
        border: '1px solid rgba(0,0,0,0.08)',
        fontSize: 12,
        fontWeight: 700,
        boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
      }}
    />
  );

  let chart: React.ReactNode = null;

  if (chart_type === 'line') {
    chart = (
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" vertical={false} />
        <XAxis dataKey={x_field} tick={AXIS_STYLE} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} width={48}
               tickFormatter={(v) => (isPercent ? `${v}%` : `₹${(v / 1000).toFixed(0)}k`)} />
        {tooltip}
        <Line type="monotone" dataKey={y_field} stroke={COLORS[0]} strokeWidth={2.5}
              dot={{ r: 3, fill: COLORS[0] }} activeDot={{ r: 5 }} animationDuration={700} />
      </LineChart>
    );
  } else if (chart_type === 'bar') {
    chart = (
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" vertical={false} />
        <XAxis dataKey={x_field} tick={AXIS_STYLE} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} width={48}
               tickFormatter={(v) => (isPercent ? `${v}%` : `₹${(v / 1000).toFixed(0)}k`)} />
        {tooltip}
        <Bar dataKey={y_field} radius={[6, 6, 0, 0]} animationDuration={700}>
          {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
        </Bar>
      </BarChart>
    );
  } else if (chart_type === 'pie') {
    chart = (
      <PieChart>
        <Pie data={data} dataKey={y_field} nameKey={x_field} cx="50%" cy="50%"
             innerRadius={45} outerRadius={75} paddingAngle={3} stroke="none" animationDuration={700}>
          {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
        </Pie>
        {tooltip}
        <Legend verticalAlign="bottom" iconType="circle"
                wrapperStyle={{ fontSize: 10, fontWeight: 700 }} />
      </PieChart>
    );
  } else {
    return null;
  }

  return (
    <div className="mt-3 bg-surface-container-lowest p-3 rounded-xl border border-outline-variant/40">
      {title && (
        <p className="text-[10px] font-black text-on-surface-variant uppercase tracking-widest mb-2 px-1">
          {title}
        </p>
      )}
      <div className="w-full h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          {chart as React.ReactElement}
        </ResponsiveContainer>
      </div>
    </div>
  );
};
