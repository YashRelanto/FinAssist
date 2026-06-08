
import React, { useState, useEffect } from 'react';
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
  status?: string;
  test_mape?: number | null;
  trained_users?: number | null;
  trained_at?: string | null;
  deployable?: boolean;
  label?: string;
};

function formatMape(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function formatDriftLevel(drift: Record<string, unknown>): string {
  const level = drift.drift_level;
  if (typeof level === 'string' && level) return level;
  const status = drift.status;
  if (typeof status === 'string' && status) return status;
  return '—';
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
            {run.label ?? run.job_id}
            {run.trained_at ? ` · ${new Date(run.trained_at).toLocaleString()}` : ''}
            {run.status && run.status !== 'completed' ? ` (${run.status})` : ''}
          </option>
        ))}
      </select>
    </label>
  );
}

function OverviewSection() {
  const [runs, setRuns] = useState<TrainRun[]>([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [data, setData] = useState<any>(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    adminGet('/train/runs')
      .then((d) => {
        const list: TrainRun[] = d.runs ?? [];
        setRuns(list);
        const firstCompleted =
          list.find((r) => r.status === 'completed') ?? list[0];
        if (firstCompleted) {
          setSelectedJobId(firstCompleted.job_id);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingRuns(false));
  }, []);

  useEffect(() => {
    if (!selectedJobId) return;
    setLoadingMetrics(true);
    setError('');
    adminGet(`/overview?job_id=${encodeURIComponent(selectedJobId)}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoadingMetrics(false));
  }, [selectedJobId]);

  if (loadingRuns) return <LoadingSpinner />;
  if (error && !data) return <ErrorBox msg={error} />;

  const run = data?.run ?? {};
  const drift = data?.drift ?? {};
  const status = run.status ?? '—';

  return (
    <div className="space-y-6">
      <RunSelector
        runs={runs}
        value={selectedJobId}
        onChange={setSelectedJobId}
        label="Training run (job id)"
      />

      {loadingMetrics ? (
        <LoadingSpinner />
      ) : (
        <>
          {error && <ErrorBox msg={error} />}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              icon={BarChart2}
              label="Test MAPE"
              value={formatMape(run.test_mape)}
              sub="Holdout weekly forecast error"
              color="text-blue-500"
            />
            <StatCard
              icon={Activity}
              label="Trained Users"
              value={run.trained_users ?? '—'}
              sub={run.trained_at ? new Date(run.trained_at).toLocaleString() : undefined}
              color="text-violet-500"
            />
            <StatCard
              icon={Cpu}
              label="Model"
              value={run.model_type ?? 'prophet'}
              sub={`Job ${selectedJobId || '—'}`}
              color="text-emerald-500"
            />
            <StatCard
              icon={AlertTriangle}
              label="Drift Level"
              value={formatDriftLevel(drift)}
              sub={
                typeof drift.mean_shift_sigma === 'number'
                  ? `σ shift ${drift.mean_shift_sigma.toFixed(2)}`
                  : typeof drift.recommendation === 'string'
                  ? drift.recommendation
                  : undefined
              }
              color={
                drift.drift_level === 'high'
                  ? 'text-orange-500'
                  : drift.drift_level === 'medium'
                  ? 'text-yellow-600'
                  : 'text-green-500'
              }
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
  const [datasets, setDatasets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    adminGet('/datasets')
      .then((d) => setDatasets(d.datasets ?? []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBox msg={error} />;

  return (
    <div className="space-y-6">
      <div className="bg-surface-variant rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-outline-variant text-left">
              <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">ID</th>
              <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Rows</th>
              <th className="px-5 py-3 text-xs font-medium text-on-surface-variant">Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {datasets.length === 0 && (
              <tr><td colSpan={3} className="px-5 py-6 text-center text-on-surface-variant text-xs">No datasets yet.</td></tr>
            )}
            {datasets.map((d: any) => (
              <tr key={d.id} className="border-b border-outline-variant last:border-0 hover:bg-surface/50 transition">
                <td className="px-5 py-3 font-mono text-xs">{d.id}</td>
                <td className="px-5 py-3 text-on-surface-variant">{d.rows ?? '—'}</td>
                <td className="px-5 py-3 text-on-surface-variant">{d.created_at ? new Date(d.created_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TrainingSection() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [datasets, setDatasets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [models, setModels] = useState<string[]>(['prophet']);
  const [datasetId, setDatasetId] = useState('default');
  const [starting, setStarting] = useState(false);
  const [startMsg, setStartMsg] = useState('');

  const MODEL_OPTIONS = ['prophet'];

  const loadJobs = () =>
    adminGet('/train/jobs')
      .then((d) => setJobs(d.jobs ?? []))
      .catch(() => {});

  useEffect(() => {
    Promise.all([
      adminGet('/train/jobs').then((d) => setJobs(d.jobs ?? [])),
      adminGet('/datasets').then((d) => setDatasets(d.datasets ?? [])),
    ])
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const toggleModel = (m: string) =>
    setModels((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));

  const startTrain = async () => {
    if (!models.length) { setStartMsg('Select at least one model.'); return; }
    setStarting(true); setStartMsg('');
    try {
      const d = await adminPost('/train', { models, dataset_id: datasetId });
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
        <div className="flex flex-wrap gap-3">
          {MODEL_OPTIONS.map((m) => (
            <button
              key={m}
              onClick={() => toggleModel(m)}
              className={`px-4 py-1.5 rounded-lg text-xs font-medium border transition ${
                models.includes(m)
                  ? 'bg-primary text-white border-primary'
                  : 'bg-surface text-on-surface border-outline-variant hover:border-primary'
              }`}
            >
              {m}
            </button>
          ))}
        </div>
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
  const [selectedJobId, setSelectedJobId] = useState('');
  const [selectedModel, setSelectedModel] = useState('prophet');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deploying, setDeploying] = useState(false);
  const [deployMsg, setDeployMsg] = useState('');

  const deployableRuns = runs.filter((r) => r.deployable && r.status === 'completed');

  useEffect(() => {
    adminGet('/train/runs')
      .then((d) => {
        const list: TrainRun[] = d.runs ?? [];
        setRuns(list);
        const first = list.find((r) => r.deployable && r.status === 'completed');
        if (first) {
          setSelectedJobId(first.job_id);
          if (first.model_type) setSelectedModel(first.model_type);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const deploy = async () => {
    if (!selectedJobId) {
      setDeployMsg('Select a training run to deploy.');
      return;
    }
    setDeploying(true);
    setDeployMsg('');
    try {
      const d = await adminPost('/deploy', {
        job_id: selectedJobId,
        models: [selectedModel],
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

  return (
    <div className="space-y-6">
      <div className="bg-surface-variant rounded-2xl p-6 space-y-4">
        <h3 className="text-sm font-semibold text-on-surface flex items-center gap-2">
          <Rocket className="w-4 h-4 text-primary" /> Deploy Training Run
        </h3>

        {deployableRuns.length === 0 ? (
          <p className="text-xs text-on-surface-variant">
            No deployable training runs yet. Complete a training job first — each run is saved by job id.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <RunSelector
              runs={deployableRuns}
              value={selectedJobId}
              onChange={(jobId) => {
                setSelectedJobId(jobId);
                const run = runs.find((r) => r.job_id === jobId);
                if (run?.model_type) setSelectedModel(run.model_type);
              }}
              label="Training run (job id)"
            />
            <label className="block">
              <span className="text-xs text-on-surface-variant mb-1 block">Model</span>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full text-sm bg-surface border border-outline-variant rounded-lg px-3 py-2 text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="prophet">prophet</option>
              </select>
            </label>
          </div>
        )}

        {selectedRun && (
          <div className="bg-surface rounded-lg px-4 py-3 text-xs space-y-1">
            <div className="flex items-center gap-2">
              <Server className="w-3.5 h-3.5 text-emerald-500" />
              <span className="font-medium text-on-surface">Job {selectedRun.job_id}</span>
              <Badge status={selectedRun.status ?? 'completed'} />
            </div>
            <p className="text-on-surface-variant">
              MAPE {formatMape(selectedRun.test_mape)} · {selectedRun.trained_users ?? '—'} users
              {selectedRun.trained_at
                ? ` · trained ${new Date(selectedRun.trained_at).toLocaleString()}`
                : ''}
            </p>
          </div>
        )}

        <button
          onClick={deploy}
          disabled={deploying || !selectedJobId || deployableRuns.length === 0}
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
