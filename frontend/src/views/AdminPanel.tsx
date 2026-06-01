
import React, { useState, useEffect, useRef } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart2,
  ChevronRight,
  CloudUpload,
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

const API_BASE = 'http://localhost:8000/api/admin';

// ─── helpers ────────────────────────────────────────────────────────────────
function token() {
  return localStorage.getItem('token') ?? '';
}
async function adminGet(path: string) {
  const r = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function adminPost(path: string, body?: unknown) {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token()}`,
    },
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
    failed: 'bg-red-100 text-red-700',
    pending: 'bg-yellow-100 text-yellow-700',
  };
  const Icon =
    status === 'done'
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
function OverviewSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    adminGet('/overview')
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBox msg={error} />;

  const perf = data?.performance ?? {};
  const drift = data?.drift ?? {};

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatCard icon={BarChart2} label="MAE" value={perf.mae?.toFixed(3) ?? '—'} color="text-blue-500" />
      <StatCard icon={Activity} label="RMSE" value={perf.rmse?.toFixed(3) ?? '—'} color="text-violet-500" />
      <StatCard icon={Cpu} label="R²" value={perf.r2?.toFixed(3) ?? '—'} color="text-emerald-500" />
      <StatCard
        icon={AlertTriangle}
        label="Drift Score"
        value={drift.score?.toFixed(3) ?? '—'}
        sub={drift.status ?? ''}
        color={drift.status === 'ok' ? 'text-green-500' : 'text-orange-500'}
      />
    </div>
  );
}

function DatasetsSection() {
  const [datasets, setDatasets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const txRef = useRef<HTMLInputElement>(null);
  const catRef = useRef<HTMLInputElement>(null);

  const load = () =>
    adminGet('/datasets')
      .then((d) => setDatasets(d.datasets ?? []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  const handleUpload = async () => {
    const txFile = txRef.current?.files?.[0];
    if (!txFile) { setUploadMsg('Select a transactions CSV first.'); return; }
    setUploading(true);
    setUploadMsg('');
    try {
      const form = new FormData();
      form.append('transactions', txFile);
      if (catRef.current?.files?.[0]) form.append('categories', catRef.current.files[0]);
      const r = await fetch(`${API_BASE}/dataset/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token()}` },
        body: form,
      });
      if (!r.ok) throw new Error(await r.text());
      setUploadMsg('✅ Dataset uploaded successfully!');
      load();
    } catch (e: any) {
      setUploadMsg(`❌ ${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBox msg={error} />;

  return (
    <div className="space-y-6">
      {/* Upload */}
      <div className="bg-surface-variant rounded-2xl p-6 space-y-4">
        <h3 className="text-sm font-semibold text-on-surface flex items-center gap-2">
          <CloudUpload className="w-4 h-4 text-primary" /> Upload New Dataset
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-on-surface-variant mb-1 block">transactions.csv *</span>
            <input ref={txRef} type="file" accept=".csv" className="block w-full text-sm text-on-surface-variant file:mr-3 file:py-1.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-primary file:text-white hover:file:bg-primary/80 cursor-pointer" />
          </label>
          <label className="block">
            <span className="text-xs text-on-surface-variant mb-1 block">categories.csv (optional)</span>
            <input ref={catRef} type="file" accept=".csv" className="block w-full text-sm text-on-surface-variant file:mr-3 file:py-1.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-surface file:text-on-surface hover:file:bg-surface/80 cursor-pointer" />
          </label>
        </div>
        <button
          onClick={handleUpload}
          disabled={uploading}
          className="inline-flex items-center gap-2 px-5 py-2 bg-primary text-white rounded-xl text-sm font-medium hover:bg-primary/90 disabled:opacity-60 transition"
        >
          {uploading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CloudUpload className="w-4 h-4" />}
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
        {uploadMsg && <p className="text-sm mt-1">{uploadMsg}</p>}
      </div>

      {/* List */}
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
  const [staged, setStaged] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deploying, setDeploying] = useState(false);
  const [deployMsg, setDeployMsg] = useState('');

  const loadStaged = () =>
    adminGet('/staging')
      .then((d) => setStaged(d.staged ?? []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

  useEffect(() => { loadStaged(); }, []);

  const deploy = async () => {
    setDeploying(true); setDeployMsg('');
    try {
      const d = await adminPost('/deploy');
      setDeployMsg(`✅ Deployed: ${(d.deployed ?? []).join(', ') || 'none'}`);
      loadStaged();
    } catch (e: any) {
      setDeployMsg(`❌ ${e.message}`);
    } finally {
      setDeploying(false);
    }
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBox msg={error} />;

  return (
    <div className="space-y-6">
      <div className="bg-surface-variant rounded-2xl p-6 space-y-4">
        <h3 className="text-sm font-semibold text-on-surface flex items-center gap-2">
          <Rocket className="w-4 h-4 text-primary" /> Staged Models
        </h3>
        {staged.length === 0 ? (
          <p className="text-xs text-on-surface-variant">No models staged for deployment.</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {staged.map((s: any) => (
              <div key={s.id} className="bg-surface rounded-lg px-4 py-2 flex items-center gap-2 text-xs">
                <Server className="w-3.5 h-3.5 text-emerald-500" />
                <span className="font-medium text-on-surface">{s.id}</span>
                <span className="text-on-surface-variant">{s.filename}</span>
              </div>
            ))}
          </div>
        )}
        <button
          onClick={deploy}
          disabled={deploying || staged.length === 0}
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
