'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
      <div className="min-w-0">
        {eyebrow && (
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--primary)] mb-2">
            {eyebrow}
          </p>
        )}
        <h1 className="text-2xl sm:text-3xl md:text-[2rem] font-bold tracking-tight leading-tight">
          {title}
        </h1>
        {description && (
          <p className="cf-secondary mt-2 text-sm sm:text-[0.95rem] max-w-2xl leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  accent = 'primary',
  delayClass = '',
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
  accent?: 'primary' | 'success' | 'warning' | 'info';
  delayClass?: string;
}) {
  const accents = {
    primary: 'from-violet-500/15 to-transparent text-violet-400',
    success: 'from-emerald-500/15 to-transparent text-emerald-400',
    warning: 'from-amber-500/15 to-transparent text-amber-400',
    info: 'from-sky-500/15 to-transparent text-sky-400',
  };

  return (
    <div
      className={`cf-card relative overflow-hidden p-5 cf-animate-in ${delayClass}`}
    >
      <div
        className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${accents[accent]} opacity-80`}
      />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide cf-muted">{label}</p>
          <p className="text-2xl sm:text-3xl font-bold tracking-tight mt-2 tabular-nums">{value}</p>
          {hint && <p className="text-xs cf-muted mt-1.5 leading-snug">{hint}</p>}
        </div>
        {icon && (
          <div className="shrink-0 w-10 h-10 rounded-xl bg-[var(--card)]/80 border border-[var(--card-border)] flex items-center justify-center">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-4">
      {icon && (
        <div className="w-12 h-12 rounded-2xl bg-[var(--primary-soft)] border border-[var(--primary-border)] flex items-center justify-center mb-4 text-[var(--primary)]">
          {icon}
        </div>
      )}
      <p className="font-semibold">{title}</p>
      {description && <p className="text-sm cf-muted mt-1.5 max-w-sm leading-relaxed">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function QuickActionCard({
  href,
  icon,
  title,
  description,
  cta,
}: {
  href: string;
  icon: ReactNode;
  title: string;
  description: string;
  cta: string;
}) {
  return (
    <Link href={href} className="cf-card cf-card-interactive group p-6 block h-full">
      <div className="w-11 h-11 rounded-2xl bg-[var(--primary-soft)] border border-[var(--primary-border)] flex items-center justify-center text-[var(--primary)] mb-4 group-hover:scale-105 transition-transform">
        {icon}
      </div>
      <h3 className="text-base font-semibold tracking-tight">{title}</h3>
      <p className="text-sm cf-muted mt-2 leading-relaxed">{description}</p>
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--primary)] mt-5 group-hover:gap-2.5 transition-all">
        {cta} <ArrowRight className="w-4 h-4" />
      </span>
    </Link>
  );
}

export function SectionCard({
  title,
  icon,
  action,
  children,
  className = '',
}: {
  title: string;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`cf-card p-5 sm:p-6 ${className}`}>
      <div className="flex items-center justify-between gap-3 mb-5">
        <h2 className="cf-section-title">
          {icon}
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}
