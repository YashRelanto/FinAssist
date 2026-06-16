
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart2,
  ChevronRight,
  Cpu,
  Database,
  PlayCircle,
  RefreshCw,
  Rocket,
  Server,
  CheckCircle2,
  Clock,
  XCircle,
} from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { loadAuthSession } from '../lib/authSession';
import { activeUserId } from '../lib/activeUserId';

const API_BASE = 'http://localhost:8000/api/admin';

// ─── helpers ────────────────────────────────────────────────────────────────
function adminHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const session = loadAuthSession();
  const uid = activeUserId(session?.user);
  if (!uid) {
    throw new Error('Not signed in');
  }
  const headers: Record<string, string> = {
    'X-User-Id': uid,
    ...extra,
  };
  const token = session?.accessToken ?? localStorage.getItem('token');
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function adminGet(path: string) {
  const r = await fetch(`${API_BASE}${path}`, {
    headers: adminHeaders(),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function adminPost(path: string, body?: unknown) {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: adminHeaders({ 'Content-Type': 'application/json' }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ─── sub-components ──────────────────────────────────────────────────────────
function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = 'text-primary',
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-surface-variant rounded-2xl p-5 flex items-start gap-4 shadow-sm">
      <div className={`p-3 rounded-xl bg-surface ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs text-on-surface-variant mb-1">{label}</p>
        <p className="text-xl font-bold text-on-surface">{value}</p>
        {sub && <p className="text-xs text-on-surface-variant mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function Badge({ status }: { status: string }) {
  const map: Record<string, string> = {
    running: 'bg-blue-100 text-blue-700',
    done: 'bg-green-100 text-green-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    pending: 'bg-yellow-100 text-yellow-700',
    queued: 'bg-yellow-100 text-yellow-700',
  };
  const Icon =
    status === 'done' || status === 'completed'
      ? CheckCircle2
      : status === 'failed'
      ? XCircle
      : status === 'running'
      ? RefreshCw
      : Clock;
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-0.5 rounded-full ${
        map[status] ?? 'bg-gray-100 text-gray-600'
      }`}
    >
      <Icon className={`w-3 h-3 ${status === 'running' ? 'animate-spin' : ''}`} />
      {status}
    </span>
  );
}

// ─── sections ───────────────────────────────────────────────────────────────
type TrainRun = {
  job_id: string;
  model_type?: string;
  training_mode?: string;
  status?: string;
  test_mape?: number | null;
  trained_users?: number | null;
  trained_transactions?: number | null;
  trained_at?: string | null;
  deployable?: boolean;
  label?: string;
};

const PROPHET_MODES = [{ id: 'prophet', label: 'Prophet (global monthly)' }] as const;

type ProphetModeId = (typeof PROPHET_MODES)[number]['id'];

function modeLabel(mode: string | undefined): string {
  if (mode === 'prophet_default') return 'Prophet (global monthly)';
  return PROPHET_MODES.find((m) => m.id === mode)?.label ?? mode ?? 'prophet';
}

function runMatchesMode(run: TrainRun, mode: ProphetModeId): boolean {
  const runMode = run.model_type ?? 'prophet';
  if (mode === 'prophet') return runMode === 'prophet' || runMode === 'prophet_default';
  return runMode === mode;
}

function formatRunOption(run: TrainRun): string {
  const mode = modeLabel(run.model_type);
  const base = run.label ?? run.job_id;
  const when = run.trained_at ? ` · ${new Date(run.trained_at).toLocaleString()}` : '';
  const status = run.status && run.status !== 'completed' ? ` (${run.status})` : '';
  return `${mode} — ${base}${when}${status}`;
}

function formatMape(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function defaultModeFromRuns(_runs: TrainRun[]): ProphetModeId {
  return 'prophet';
}

function useInitialMode(runs: TrainRun[], mode: ProphetModeId, setMode: (m: ProphetModeId) => void) {
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current || runs.length === 0) return;
    setMode(defaultModeFromRuns(runs));
    initialized.current = true;
  }, [runs, setMode]);
}

function useAutoSelectRun(
  options: TrainRun[],
  selectedJobId: string,
  setSelectedJobId: (id: string) => void,
) {
  useEffect(() => {
    if (selectedJobId && options.some((r) => r.job_id === selectedJobId)) {
      return;
    }
    const first =
      options.find((r) => r.status === 'completed') ?? options[0];
    setSelectedJobId(first?.job_id ?? '');
  }, [options, selectedJobId, setSelectedJobId]);
}

function RunSelector({
  runs,
  value,
  onChange,
  label,
  filter,
}: {
  runs: TrainRun[];
  value: string;
  onChange: (jobId: string) => void;
  label: string;
  filter?: (run: TrainRun) => boolean;
}) {
  const options = filter ? runs.filter(filter) : runs;
  return (
    <label className="block max-w-md">
      <span className="text-xs text-on-surface-variant mb-1 block">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-sm bg-surface border border-outline-variant rounded-lg px-3 py-2 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
      >
        {options.length === 0 && <option value="">No training runs available</option>}
        {options.map((run) => (
          <option key={run.job_id} value={run.job_id}>
            {formatRunOption(run)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ModeSelector({
  value,
  onChange,
  label = 'Training mode',
}: {
  value: ProphetModeId;
  onChange: (mode: ProphetModeId) => void;
  label?: string;
}) {
  return (
    <label className="block max-w-md">
      <span className="text-xs text-on-surface-variant mb-1 block">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as ProphetModeId)}
        className="w-full text-sm bg-surface border border-outline-variant rounded-lg px-3 py-2 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
      >
        {PROPHET_MODES.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function OverviewSection() {
  const [runs, setRuns] = useState<TrainRun[]>([]);
  const [mode, setMode] = useState<ProphetModeId>('prophet');
  const [selectedJobId, setSelectedJobId] = useState('');
  const [data, setData] = useState<any>(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [error, setError] = useState('');

  const filteredRuns = runs.filter((r) => runMatchesMode(r, mode));
  useInitialMode(runs, mode, setMode);
  useAutoSelectRun(filteredRuns, selectedJobId, setSelectedJobId);

  const loadRuns = useCallback(() => {
    adminGet('/train/runs')
      .then((d) => setRuns(d.runs ?? []))
      .catch((e) => setError(e.message))
      .finally(() => setLoadingRuns(false));
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (!selectedJobId) return;
    setLoadingMetrics(true);
    setError('');
    adminGet(`/overview?job_id=${encodeURIComponent(selectedJobId)}`)
      .then((d) => {
        setData(d);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingMetrics(false));
  }, [selectedJobId]);

  const handleRunChange = (jobId: string) => {
    setSelectedJobId(jobId);
    const run = runs.find((r) => r.job_id === jobId);
    if (run?.model_type === 'prophet' || run?.model_type === 'prophet_default') {
      setMode(run.model_type);
    }
  };

  if (loadingRuns) return <LoadingSpinner />;
  if (error && !data) return <ErrorBox msg={error} />;

  const run = data?.run ?? {};
  const status = run.status ?? '—';

  return (
    <div className="space-y-6">
      <ModeSelector value={mode} onChange={setMode} label="Model approach" />
      <RunSelector
        runs={filteredRuns}
        value={selectedJobId}
        onChange={handleRunChange}
        label="Training run (job id)"
      />

      {loadingMetrics ? (
        <LoadingSpinner />
      ) : (
        <>
          {error && <ErrorBox msg={error} />}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <StatCard
              icon={BarChart2}
              label="Test MAPE"
              value={formatMape(run.test_mape)}
              sub="Holdout monthly forecast error"
              color="text-blue-500"
            />
            <StatCard
              icon={Database}
              label="Transactions Trained On"
              value={run.trained_transactions?.toLocaleString() ?? '—'}
              sub={
                run.trained_at
                  ? `Expense rows · users with 6+ months · ${new Date(run.trained_at).toLocaleString()}`
                  : 'Expense rows from users with 6+ months of history'
              }
              color="text-violet-500"
            />
            <StatCard
              icon={Cpu}
              label="Model"
              value={modeLabel(run.model_type)}
              sub={`Job ${selectedJobId || '—'}`}
              color="text-emerald-500"
            />
          </div>
          {status !== 'completed' && (
            <p className="text-sm text-on-surface-variant">
              Run status: <Badge status={status} />
            </p>
          )}
        </>
      )}
    </div>
  );
}

function DatasetsSection() {
  const [runs, setRuns] = useState<TrainRun[]>([]);
  const [mode, setMode] = useState<ProphetModeId>('prophet');
  const [selectedJobId, setSelectedJobId] = useState('');
  const [snapshot, setSnapshot] = useState<any>(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState('');

  const filteredRuns = runs.filter(
    (r) => r.job_id !== 'production' && runMatchesMode(r, mode),
  );
  useInitialMode(runs, mode, setMode);
  useAutoSelectRun(filteredRuns, selectedJobId, setSelectedJobId);

  useEffect(() => {
    adminGet('/train/runs')
      .then((d) => setRuns(d.runs ?? []))
      .catch((e) => setError(e.message))
      .finally(() => setLoadingRuns(false));
  }, []);

  useEffect(() => {
    if (!selectedJobId) return;
    setLoadingData(true);
    setError('');
    adminGet(`/datasets?job_id=${encodeURIComponent(selectedJobId)}`)
      .then((d) => {
        setSnapshot(d.dataset ?? null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingData(false));
  }, [selectedJobId]);

  if (loadingRuns) return <LoadingSpinner />;
  if (error && !snapshot) return <ErrorBox msg={error} />;

  const sample: any[] = snapshot?.sample ?? [];

  return (
    <div className="space-y-6">
      <ModeSelector value={mode} onChange={setMode} label="Model approach" />
      <RunSelector
        runs={filteredRuns}
        value={selectedJobId}
        onChange={setSelectedJobId}
        label="Training run (job id)"
      />

      {loadingData ? (
        <LoadingSpinner />
      ) : snapshot ? (
        <>
          {error && <ErrorBox msg={error} />}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard icon={Database} label="Training rows" value={snapshot.training_rows?.toLocaleString() ?? '—'} sub="Eligible expense transactions" color="text-violet-500" />
            <StatCard icon={Cpu} label="Training users" value={snapshot.training_users?.toLocaleString() ?? '—'} sub="Users with 6+ months history" color="text-emerald-500" />
            <StatCard icon={BarChart2} label="Total expense rows" value={snapshot.total_expense_rows?.toLocaleString() ?? '—'} sub={`On or before ${snapshot.trained_at ? new Date(snapshot.trained_at).toLocaleString() : 'train time'}`} color="text-blue-500" />
            <StatCard icon={Activity} label="Snapshot as of" value={snapshot.trained_at ? new Date(snapshot.trained_at).toLocaleDateString() : '—'} sub={`Job ${selectedJobId}`} color="text-primary" />
          </div>
          <div className="bg-surface-variant rounded-2xl overflow-hidden">
            <div className="px-5 py-3 border-b border-outline-variant text-xs font-semibold text-on-surface">
              Training data sample (up to {sample.length} rows)
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-outline-variant text-left">
                  <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">User</th>
                  <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Date</th>
                  <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Amount</th>
                </tr>
              </thead>
              <tbody>
                {sample.length === 0 && (
                  <tr><td colSpan={3} className="px-5 py-6 text-center text-on-surface-variant text-xs">No training rows for this run.</td></tr>
                )}
                {sample.map((row: any, idx: number) => (
                  <tr key={`${row.user_id}-${row.transaction_date}-${idx}`} className="border-b border-outline-variant last:border-0 hover:bg-surface/50 transition">
                    <td className="px-5 py-3 font-mono text-xs">{row.user_id}</td>
                    <td className="px-5 py-3 text-on-surface-variant">{row.transaction_date}</td>
                    <td className="px-5 py-3 text-on-surface-variant">{row.amount?.toLocaleString?.() ?? row.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="text-xs text-on-surface-variant">Select a training run to view its dataset snapshot.</p>
      )}
    </div>
  );
}

function TrainingSection() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [datasets, setDatasets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [trainingMode, setTrainingMode] = useState<ProphetModeId>('prophet');
  const [datasetId, setDatasetId] = useState('default');
  const [starting, setStarting] = useState(false);
  const [startMsg, setStartMsg] = useState('');

  const loadJobs = useCallback(() =>
    adminGet('/train/jobs')
      .then((d) => {
        const next = d.jobs ?? [];
        setJobs(next);
      })
      .catch(() => {}), []);

  useEffect(() => {
    Promise.all([
      loadJobs(),
      adminGet('/datasets').then((d) => setDatasets(d.datasets ?? [])),
    ])
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [loadJobs]);

  useEffect(() => {
    const hasActive = jobs.some(
      (j) => j.status === 'running' || j.status === 'queued' || j.status === 'pending',
    );
    if (!hasActive) return;
    const timer = window.setInterval(loadJobs, 3000);
    return () => window.clearInterval(timer);
  }, [jobs, loadJobs]);

  const startTrain = async () => {
    setStarting(true); setStartMsg('');
    try {
      const d = await adminPost('/train', { models: [trainingMode], dataset_id: datasetId });
      setStartMsg(`✅ Job started: ${d.job_id}`);
      loadJobs();
    } catch (e: any) {
      setStartMsg(`❌ ${e.message}`);
    } finally {
      setStarting(false);
    }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBox msg={error} />;

  return (
    <div className="space-y-6">
      {/* Start training */}
      <div className="bg-surface-variant rounded-2xl p-6 space-y-4">
        <h3 className="text-sm font-semibold text-on-surface flex items-center gap-2">
          <PlayCircle className="w-4 h-4 text-primary" /> Start Training Job
        </h3>
        <ModeSelector
          value={trainingMode}
          onChange={setTrainingMode}
          label="Model approach to train"
        />
        <div>
          <label className="text-xs text-on-surface-variant block mb-1">Dataset</label>
          <select
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            className="text-sm bg-surface border border-outline-variant rounded-lg px-3 py-2 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="default">default</option>
            {datasets.map((d: any) => (
              <option key={d.id} value={d.id}>{d.id}</option>
            ))}
          </select>
        </div>
        <button
          onClick={startTrain}
          disabled={starting}
          className="inline-flex items-center gap-2 px-5 py-2 bg-primary text-white rounded-xl text-sm font-medium hover:bg-primary/90 disabled:opacity-60 transition"
        >
          {starting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
          {starting ? 'Starting…' : 'Start Training'}
        </button>
        {startMsg && <p className="text-sm mt-1">{startMsg}</p>}
      </div>

      {/* Jobs list */}
      <div className="bg-surface-variant rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-outline-variant">
          <span className="text-xs font-semibold text-on-surface">Training Jobs</span>
          <button onClick={loadJobs} className="text-xs text-primary hover:underline flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-outline-variant text-left">
              <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Job ID</th>
              <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Models</th>
              <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Status</th>
              <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Started</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 && (
              <tr><td colSpan={4} className="px-5 py-6 text-center text-on-surface-variant text-xs">No jobs yet.</td></tr>
            )}
            {jobs.map((j: any) => (
              <tr key={j.job_id} className="border-b border-outline-variant last:border-0 hover:bg-surface/50 transition">
                <td className="px-5 py-3 font-mono text-xs">{j.job_id}</td>
                <td className="px-5 py-3 text-xs text-on-surface-variant">{(j.models ?? []).join(', ')}</td>
                <td className="px-5 py-3"><Badge status={j.status} /></td>
                <td className="px-5 py-3 text-on-surface-variant text-xs">{j.started_at ? new Date(j.started_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DeploySection() {
  const [runs, setRuns] = useState<TrainRun[]>([]);
  const [mode, setMode] = useState<ProphetModeId>('prophet');
  const [selectedJobId, setSelectedJobId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deploying, setDeploying] = useState(false);
  const [deployMsg, setDeployMsg] = useState('');

  const completedRuns = runs.filter(
    (r) => r.job_id !== 'production' && r.status === 'completed',
  );
  const selectableRuns = completedRuns.filter((r) => runMatchesMode(r, mode));
  useInitialMode(runs, mode, setMode);
  useAutoSelectRun(selectableRuns, selectedJobId, setSelectedJobId);

  const loadRuns = useCallback(() => {
    adminGet('/train/runs')
      .then((d) => {
        const list = d.runs ?? [];
        setRuns(list);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const deploy = async () => {
    if (!selectedJobId) {
      setDeployMsg('Select a training run to deploy.');
      return;
    }
    setDeploying(true);
    setDeployMsg('');
    try {
      const run = runs.find((r) => r.job_id === selectedJobId);
      const modelType = run?.model_type ?? mode;
      const d = await adminPost('/deploy', {
        job_id: selectedJobId,
        models: [modelType],
      });
      setDeployMsg(
        `✅ Deployed job ${d.job_id ?? selectedJobId}: ${(d.deployed ?? []).join(', ') || 'none'}`,
      );
    } catch (e: any) {
      setDeployMsg(`❌ ${e.message}`);
    } finally {
      setDeploying(false);
    }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBox msg={error} />;

  const selectedRun = runs.find((r) => r.job_id === selectedJobId);
  const canDeploy = Boolean(selectedRun?.deployable);

  return (
    <div className="space-y-6">
      <div className="bg-surface-variant rounded-2xl p-6 space-y-4">
        <h3 className="text-sm font-semibold text-on-surface flex items-center gap-2">
          <Rocket className="w-4 h-4 text-primary" /> Deploy Training Run
        </h3>

        {completedRuns.length === 0 ? (
          <p className="text-xs text-on-surface-variant">
            No completed training runs yet. Finish a training job first — each run is saved by job id.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ModeSelector value={mode} onChange={setMode} label="Model approach" />
            <RunSelector
              runs={selectableRuns}
              value={selectedJobId}
              onChange={setSelectedJobId}
              label="Training run (job id)"
            />
          </div>
        )}

        <div className="bg-surface-variant rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-outline-variant text-xs font-semibold text-on-surface">
            All training runs
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-outline-variant text-left">
                <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Job ID</th>
                <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Model</th>
                <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Status</th>
                <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">MAPE</th>
                <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Trained</th>
              </tr>
            </thead>
            <tbody>
              {completedRuns.length === 0 && (
                <tr><td colSpan={5} className="px-5 py-6 text-center text-on-surface-variant text-xs">No runs yet.</td></tr>
              )}
              {completedRuns.map((run) => (
                <tr key={run.job_id} className="border-b border-outline-variant last:border-0 hover:bg-surface/50 transition">
                  <td className="px-5 py-3 font-mono text-xs">{run.job_id}</td>
                  <td className="px-5 py-3 text-xs text-on-surface-variant">{modeLabel(run.model_type)}</td>
                  <td className="px-5 py-3"><Badge status={run.status ?? 'completed'} /></td>
                  <td className="px-5 py-3 text-on-surface-variant text-xs">{formatMape(run.test_mape)}</td>
                  <td className="px-5 py-3 text-on-surface-variant text-xs">{run.trained_at ? new Date(run.trained_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selectedRun && (
          <div className="bg-surface rounded-lg px-4 py-3 text-xs space-y-1">
            <div className="flex items-center gap-2">
              <Server className="w-3.5 h-3.5 text-emerald-500" />
              <span className="font-medium text-on-surface">Job {selectedRun.job_id}</span>
              <Badge status={selectedRun.status ?? 'completed'} />
            </div>
            <p className="text-on-surface-variant">
              MAPE {formatMape(selectedRun.test_mape)} ·{' '}
              {selectedRun.trained_transactions?.toLocaleString() ?? '—'} transactions
              {selectedRun.trained_at
                ? ` · trained ${new Date(selectedRun.trained_at).toLocaleString()}`
                : ''}
            </p>
          </div>
        )}

        <button
          onClick={deploy}
          disabled={deploying || !selectedJobId || !canDeploy || selectableRuns.length === 0}
          className="inline-flex items-center gap-2 px-5 py-2 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 disabled:opacity-60 transition"
        >
          {deploying ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />}
          {deploying ? 'Deploying…' : 'Deploy to Production'}
        </button>
        {deployMsg && <p className="text-sm mt-1">{deployMsg}</p>}
      </div>
    </div>
  );
}

// ─── shared utils ────────────────────────────────────────────────────────────
function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <RefreshCw className="w-6 h-6 animate-spin text-primary" />
    </div>
  );
}
function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex items-start gap-2">
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
      <span>{msg}</span>
    </div>
  );
}

// ─── main component ──────────────────────────────────────────────────────────
const TABS = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'datasets', label: 'Datasets', icon: Database },
  { id: 'training', label: 'Training', icon: Cpu },
  { id: 'deploy', label: 'Deploy', icon: Rocket },
];

export const AdminPanel: React.FC = () => {
  const { user } = useAppContext();
  const [tab, setTab] = useState('overview');

  if (user.role !== 'admin') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <AlertTriangle className="w-12 h-12 text-orange-400" />
        <h2 className="text-xl font-semibold text-on-surface">Access Denied</h2>
        <p className="text-on-surface-variant text-sm">Admin privileges required.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-on-surface flex items-center gap-2">
          <Server className="w-6 h-6 text-primary" /> Admin Panel
        </h1>
        <p className="text-on-surface-variant text-sm mt-1">
          Model monitoring, training, and deployment management
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-surface-variant p-1 rounded-2xl w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition ${
              tab === id
                ? 'bg-primary text-white shadow'
                : 'text-on-surface-variant hover:text-on-surface hover:bg-surface'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
            {tab === id && <ChevronRight className="w-3 h-3 opacity-60" />}
          </button>
        ))}
      </div>

      {/* Content */}
      <div>
        {tab === 'overview' && <OverviewSection />}
        {tab === 'datasets' && <DatasetsSection />}
        {tab === 'training' && <TrainingSection />}
        {tab === 'deploy' && <DeploySection />}
      </div>
    </div>
  );
};
