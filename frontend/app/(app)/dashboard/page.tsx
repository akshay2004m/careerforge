'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  FileText,
  Mic,
  Briefcase,
  Sparkles,
  TrendingUp,
  Target,
  Award,
  Building2,
  Activity,
  ArrowUpRight,
  Trash2,
} from 'lucide-react';
import { api, type AnalyticsSummary, type UserProfile } from '@/lib/api';
import ATSScore from '@/components/ATSScore';
import {
  PageHeader,
  StatCard,
  EmptyState,
  QuickActionCard,
  SectionCard,
} from '@/components/ui';

const PIPELINE = [
  { key: 'wishlist', label: 'Wishlist', color: 'bg-zinc-400' },
  { key: 'applied', label: 'Applied', color: 'bg-sky-500' },
  { key: 'interview', label: 'Interview', color: 'bg-violet-500' },
  { key: 'offer', label: 'Offer', color: 'bg-emerald-500' },
  { key: 'rejected', label: 'Rejected', color: 'bg-rose-400' },
] as const;

function formatRelative(iso?: string | null) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${Math.max(1, mins)}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

function statusBadgeClass(status: string) {
  const s = status.toLowerCase();
  if (s.includes('offer') || s.includes('ats')) return 'cf-badge cf-badge-success';
  if (s.includes('interview')) return 'cf-badge cf-badge-primary';
  if (s.includes('reject')) return 'cf-badge cf-badge-danger';
  if (s.includes('applied')) return 'cf-badge cf-badge-info';
  return 'cf-badge cf-badge-muted';
}

export default function DashboardPage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [stats, setStats] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const handleDeleteActivity = async (type: string, id: number) => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;

      // Optimistic update
      setStats((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          recent_activity: prev.recent_activity.filter(
            (item) => !(item.type === type && item.id === id)
          ),
        };
      });

      if (type === 'application') {
        await api.deleteApplication(id);
      } else if (type === 'optimization') {
        await api.deleteOptimization(id);
      }
    } catch (e) {
      console.error('Failed to delete activity:', e);
      setError(e instanceof Error ? e.message : 'Failed to delete activity');
    }
  };

  useEffect(() => {
    let cancelled = false;
    const id = window.setTimeout(() => {
      (async () => {
        try {
          const [me, analytics] = await Promise.all([api.me(), api.analytics()]);
          if (cancelled) return;
          setUser(me);
          setStats(analytics);
        } catch (e) {
          if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load dashboard');
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="cf-skeleton h-24 w-full max-w-lg" />
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="cf-skeleton h-28" />
          ))}
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <div className="cf-skeleton h-56" />
          <div className="cf-skeleton h-56" />
        </div>
      </div>
    );
  }

  const by = stats?.by_status || {};
  const pipelineTotal = PIPELINE.reduce((sum, s) => sum + (by[s.key] || 0), 0) || 1;
  const firstName = user?.name?.split(' ')[0] || 'there';
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  return (
    <div className="space-y-8 pb-4">
      {/* Hero */}
      <div className="cf-card relative overflow-hidden p-6 sm:p-8 cf-animate-in">
        <div className="pointer-events-none absolute -top-24 -right-16 w-72 h-72 rounded-full bg-violet-500/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-20 -left-10 w-56 h-56 rounded-full bg-fuchsia-500/10 blur-3xl" />
        <div className="relative flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--primary)] mb-2">
              {greeting}
            </p>
            <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight">
              Hi, {firstName}
              <span className="text-[var(--primary)]">.</span>
            </h1>
            <p className="cf-secondary mt-2 max-w-xl text-sm sm:text-base leading-relaxed">
              {user?.headline
                ? user.headline
                : 'Track applications, polish resumes, and practice interviews — all in one place.'}
            </p>
            <div className="flex flex-wrap gap-2 mt-5">
              <Link href="/optimizer" className="cf-btn cf-btn-primary px-4 py-2.5 text-sm">
                Optimize resume
              </Link>
              <Link href="/applications" className="cf-btn cf-btn-secondary px-4 py-2.5 text-sm">
                View pipeline
              </Link>
            </div>
          </div>

          <div className="flex items-center gap-5 shrink-0 rounded-2xl border border-[var(--card-border)] bg-[var(--background)]/50 backdrop-blur px-5 py-4">
            <ATSScore score={stats?.best_ats || 0} size={84} label="Best ATS" />
            <div className="space-y-2 text-sm">
              <div>
                <p className="cf-muted text-xs">Avg ATS</p>
                <p className="font-semibold tabular-nums text-lg">
                  {stats?.average_ats ? `${Math.round(stats.average_ats)}%` : '—'}
                </p>
              </div>
              <div>
                <p className="cf-muted text-xs">Offer rate</p>
                <p className="font-semibold tabular-nums text-lg">
                  {stats?.success_rate != null ? `${Math.round(stats.success_rate)}%` : '—'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-[var(--danger)]/30 bg-[var(--danger-soft)] text-[var(--danger)] px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* KPI row — one metric per card (fixes crowded dual-metric card) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <StatCard
          label="Applications"
          value={stats?.total_applications ?? 0}
          hint="In your tracker"
          icon={<Briefcase className="w-4 h-4 text-violet-400" />}
          accent="primary"
          delayClass="cf-delay-1"
        />
        <StatCard
          label="Optimizations"
          value={stats?.total_optimizations ?? 0}
          hint={`${stats?.total_resumes ?? 0} resume versions`}
          icon={<FileText className="w-4 h-4 text-sky-400" />}
          accent="info"
          delayClass="cf-delay-2"
        />
        <StatCard
          label="Avg ATS"
          value={stats?.average_ats ? `${Math.round(stats.average_ats)}%` : '—'}
          hint="Across tailored resumes"
          icon={<Target className="w-4 h-4 text-amber-400" />}
          accent="warning"
          delayClass="cf-delay-3"
        />
        <StatCard
          label="Offer rate"
          value={stats?.success_rate != null ? `${Math.round(stats.success_rate)}%` : '—'}
          hint="Among decided outcomes"
          icon={<Award className="w-4 h-4 text-emerald-400" />}
          accent="success"
          delayClass="cf-delay-4"
        />
      </div>

      {/* Pipeline + companies */}
      <div className="grid lg:grid-cols-5 gap-4">
        <SectionCard
          className="lg:col-span-3 cf-animate-in cf-delay-2"
          title="Application pipeline"
          icon={<TrendingUp className="w-4 h-4 text-[var(--primary)]" />}
          action={
            <Link
              href="/applications"
              className="text-xs font-medium text-[var(--primary)] hover:underline inline-flex items-center gap-1"
            >
              Manage <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          }
        >
          {/* Visual bar */}
          <div className="h-3 rounded-full overflow-hidden flex bg-[var(--background)] border border-[var(--card-border)] mb-5">
            {PIPELINE.map((s) => {
              const n = by[s.key] || 0;
              if (!n) return null;
              const pct = Math.max(4, (n / pipelineTotal) * 100);
              return (
                <div
                  key={s.key}
                  className={`${s.color} h-full transition-all`}
                  style={{ width: `${pct}%` }}
                  title={`${s.label}: ${n}`}
                />
              );
            })}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
            {PIPELINE.map((s) => (
              <div
                key={s.key}
                className="rounded-xl border border-[var(--card-border)] bg-[var(--background)]/40 px-3 py-3"
              >
                <div className="flex items-center gap-1.5 mb-2">
                  <span className={`w-1.5 h-1.5 rounded-full ${s.color}`} />
                  <p className="text-[11px] font-medium cf-muted truncate">{s.label}</p>
                </div>
                <p className="text-xl font-bold tabular-nums tracking-tight">{by[s.key] || 0}</p>
              </div>
            ))}
          </div>
          <p className="text-[11px] cf-muted mt-4 leading-relaxed">
            Offer rate is calculated from interview, offer, and rejected stages.
          </p>
        </SectionCard>

        <SectionCard
          className="lg:col-span-2 cf-animate-in cf-delay-3"
          title="Top companies"
          icon={<Building2 className="w-4 h-4 text-[var(--primary)]" />}
        >
          {(stats?.top_companies || []).length === 0 ? (
            <EmptyState
              icon={<Building2 className="w-5 h-5" />}
              title="No companies yet"
              description="Add applications to see where you’re focusing."
              action={
                <Link href="/applications" className="cf-btn cf-btn-primary px-4 py-2 text-sm">
                  Add application
                </Link>
              }
            />
          ) : (
            <div className="space-y-2.5">
              {stats!.top_companies.map((c, i) => {
                const max = stats!.top_companies[0]?.count || 1;
                const width = Math.max(12, (c.count / max) * 100);
                return (
                  <div key={c.company} className="group">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-sm font-medium truncate flex items-center gap-2">
                        <span className="text-[11px] tabular-nums cf-muted w-4">{i + 1}</span>
                        {c.company}
                      </span>
                      <span className="text-xs font-semibold tabular-nums text-[var(--primary)]">
                        {c.count}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-[var(--background)] border border-[var(--card-border)] overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 transition-all"
                        style={{ width: `${width}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </SectionCard>
      </div>

      {/* Quick actions */}
      <div>
        <PageHeader title="Quick actions" description="Jump into the workflows that move your search forward." />
        <div className="grid sm:grid-cols-3 gap-4 -mt-4">
          <QuickActionCard
            href="/optimizer"
            icon={<FileText className="w-5 h-5" />}
            title="Optimize a resume"
            description="Tailor a saved version to any JD with ATS scoring and cover letter."
            cta="Open optimizer"
          />
          <QuickActionCard
            href="/interview"
            icon={<Mic className="w-5 h-5" />}
            title="Practice interview"
            description="Common + role-specific questions with live Whisper transcription."
            cta="Start practicing"
          />
          <QuickActionCard
            href="/applications"
            icon={<Briefcase className="w-5 h-5" />}
            title="Application tracker"
            description="Move roles through Applied → Interview → Offer or Rejected."
            cta="Open tracker"
          />
        </div>
      </div>

      {/* Activity */}
      <SectionCard
        title="Recent activity"
        icon={<Activity className="w-4 h-4 text-[var(--primary)]" />}
        action={
          <span className="text-xs cf-muted inline-flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5" /> Live from your workspace
          </span>
        }
      >
        {(stats?.recent_activity || []).length === 0 ? (
          <EmptyState
            icon={<Sparkles className="w-5 h-5" />}
            title="Nothing here yet"
            description="Optimize a resume or add an application to see activity."
            action={
              <Link href="/optimizer" className="cf-btn cf-btn-primary px-4 py-2 text-sm">
                Get started
              </Link>
            }
          />
        ) : (
          <ul className="divide-y divide-[var(--card-border)] -mx-1">
            {stats!.recent_activity.map((item) => (
              <li
                key={`${item.type}-${item.id}-${item.at}`}
                className="group flex items-center justify-between gap-4 px-1 py-3.5 first:pt-0 last:pb-0"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div
                    className={`mt-0.5 w-9 h-9 rounded-xl border border-[var(--card-border)] flex items-center justify-center shrink-0 ${
                      item.type === 'application'
                        ? 'bg-[var(--info-soft)] text-[var(--info)]'
                        : 'bg-[var(--primary-soft)] text-[var(--primary)]'
                    }`}
                  >
                    {item.type === 'application' ? (
                      <Briefcase className="w-4 h-4" />
                    ) : (
                      <FileText className="w-4 h-4" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate leading-snug">{item.title || '—'}</p>
                    <p className="text-xs cf-muted mt-0.5 capitalize">
                      {item.type}
                      {item.at ? ` · ${formatRelative(item.at)}` : ''}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`${statusBadgeClass(item.status)} shrink-0`}>{item.status}</span>
                  <button
                    onClick={() => handleDeleteActivity(item.type, item.id)}
                    className="p-1.5 text-[var(--muted)] hover:text-[var(--danger)] hover:bg-[var(--danger-soft)] rounded-md transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                    title="Delete activity"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}
