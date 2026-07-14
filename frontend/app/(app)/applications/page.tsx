'use client';

import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { api, type Application, type ResumeSummary } from '@/lib/api';

const STATUSES = ['wishlist', 'applied', 'interview', 'offer', 'rejected'] as const;

const statusColor: Record<string, string> = {
  wishlist: 'bg-zinc-500/20 text-zinc-400',
  applied: 'bg-blue-500/15 text-blue-400',
  interview: 'bg-purple-500/15 text-purple-400',
  offer: 'bg-green-500/15 text-green-400',
  rejected: 'bg-red-500/15 text-red-400',
};

export default function ApplicationsPage() {
  const [items, setItems] = useState<Application[]>([]);
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    company: '',
    role: '',
    status: 'applied',
    job_description: '',
    notes: '',
    resume_id: '',
  });
  const [skillsPreview, setSkillsPreview] = useState<string[]>([]);
  const [extracting, setExtracting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [apps, res] = await Promise.all([api.listApplications(), api.listResumes()]);
      setItems(apps);
      setResumes(res);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const id = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  const filtered = useMemo(() => {
    if (filter === 'all') return items;
    return items.filter((i) => i.status === filter);
  }, [items, filter]);

  const extractSkills = async () => {
    if (form.job_description.trim().length < 20) {
      toast.error('Paste a fuller job description first');
      return;
    }
    setExtracting(true);
    try {
      const data = await api.extractSkills(form.job_description);
      setSkillsPreview(data.skills);
      toast.success(`Found ${data.skills.length} skills`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Skill extract failed');
    } finally {
      setExtracting(false);
    }
  };

  const create = async () => {
    if (!form.company.trim() || !form.role.trim()) {
      toast.error('Company and role are required');
      return;
    }
    try {
      await api.createApplication({
        company: form.company,
        role: form.role,
        status: form.status,
        job_description: form.job_description || undefined,
        notes: form.notes || undefined,
        resume_id: form.resume_id ? Number(form.resume_id) : undefined,
        skills: skillsPreview.length ? skillsPreview : undefined,
      });
      toast.success('Application added');
      setShowForm(false);
      setForm({
        company: '',
        role: '',
        status: 'applied',
        job_description: '',
        notes: '',
        resume_id: '',
      });
      setSkillsPreview([]);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Create failed');
    }
  };

  const setStatus = async (id: number, status: string) => {
    try {
      const updated = await api.updateApplication(id, { status });
      setItems((prev) => prev.map((a) => (a.id === id ? updated : a)));
      toast.success(`Moved to ${status}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Update failed');
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteApplication(id);
      setItems((prev) => prev.filter((a) => a.id !== id));
      toast.success('Deleted');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Delete failed');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight">Application Tracker</h1>
          <p className="cf-muted mt-2">
            Track Applied / Interview / Offer / Rejected — with JD skills attached.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="bg-purple-600 hover:bg-purple-700 px-4 py-2.5 rounded-xl text-sm font-medium flex items-center gap-2 text-white"
        >
          <Plus className="w-4 h-4" />
          {showForm ? 'Close' : 'Add application'}
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setFilter('all')}
          className={`px-3 py-1.5 rounded-xl text-xs font-medium ${
            filter === 'all' ? 'bg-purple-600 text-white' : 'cf-card'
          }`}
        >
          All ({items.length})
        </button>
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium capitalize ${
              filter === s ? 'bg-purple-600 text-white' : 'cf-card'
            }`}
          >
            {s} ({items.filter((i) => i.status === s).length})
          </button>
        ))}
      </div>

      {showForm && (
        <div className="cf-card p-6 space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <input
              className="cf-input px-4 py-3"
              placeholder="Company"
              value={form.company}
              onChange={(e) => setForm({ ...form, company: e.target.value })}
            />
            <input
              className="cf-input px-4 py-3"
              placeholder="Role / title"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
            />
            <select
              className="cf-input px-4 py-3"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              className="cf-input px-4 py-3"
              value={form.resume_id}
              onChange={(e) => setForm({ ...form, resume_id: e.target.value })}
            >
              <option value="">Link resume (optional)</option>
              {resumes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title || `Resume #${r.id}`}
                  {r.is_primary ? ' ★' : ''}
                </option>
              ))}
            </select>
          </div>
          <textarea
            className="cf-input px-4 py-3 w-full h-28 resize-none"
            placeholder="Job description (optional — used for skill extraction)"
            value={form.job_description}
            onChange={(e) => setForm({ ...form, job_description: e.target.value })}
          />
          <div className="flex flex-wrap gap-2">
            <button
              onClick={extractSkills}
              disabled={extracting}
              className="px-4 py-2 rounded-xl text-sm border border-[var(--card-border)]"
            >
              {extracting ? 'Extracting…' : 'Extract skills from JD'}
            </button>
            <button
              onClick={create}
              className="px-4 py-2 rounded-xl text-sm bg-purple-600 text-white"
            >
              Save application
            </button>
          </div>
          {skillsPreview.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {skillsPreview.map((s) => (
                <span
                  key={s}
                  className="text-xs px-2.5 py-1 rounded-lg border border-[var(--card-border)]"
                >
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 cf-card" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="cf-card p-12 text-center">
          <p className="cf-muted">No applications in this view.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((item) => (
            <div key={item.id} className="cf-card p-5 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-lg">
                    {item.role}{' '}
                    <span className="cf-muted font-normal">@ {item.company}</span>
                  </p>
                  <div className="flex flex-wrap items-center gap-2 mt-2">
                    <span
                      className={`text-xs px-2.5 py-1 rounded-full capitalize ${
                        statusColor[item.status] || statusColor.applied
                      }`}
                    >
                      {item.status}
                    </span>
                    {item.ats_score != null && (
                      <span className="text-xs text-green-500 font-medium">
                        ATS {Math.round(item.ats_score)}%
                      </span>
                    )}
                    {item.updated_at && (
                      <span className="text-xs cf-muted">
                        {new Date(item.updated_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => remove(item.id)}
                  className="text-red-400 hover:text-red-300 p-2"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              <div className="flex flex-wrap gap-2">
                {STATUSES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setStatus(item.id, s)}
                    disabled={item.status === s}
                    className={`px-2.5 py-1 rounded-lg text-xs capitalize border border-[var(--card-border)] disabled:opacity-40 ${
                      item.status === s ? 'bg-purple-600 text-white border-purple-600' : ''
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>

              {(item.skills || []).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {item.skills!.slice(0, 12).map((s) => (
                    <span
                      key={s}
                      className="text-[11px] px-2 py-0.5 rounded-md border border-[var(--card-border)] cf-muted"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
