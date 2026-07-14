'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Sparkles, FileText, Mic, Briefcase, ArrowRight } from 'lucide-react';

export default function LandingPage() {
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => {
      setHasToken(Boolean(localStorage.getItem('token')));
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] cf-page">
      <nav className="border-b border-[var(--card-border)] bg-[var(--card)]/70 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-4 flex justify-between items-center gap-4">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center shadow-lg shadow-violet-500/20 shrink-0">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-lg sm:text-xl tracking-tight truncate">
              CareerForge AI
            </span>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            {hasToken ? (
              <Link href="/dashboard" className="cf-btn cf-btn-primary px-4 sm:px-5 py-2.5 text-sm">
                Open Dashboard
              </Link>
            ) : (
              <>
                <Link
                  href="/auth/login"
                  className="cf-btn cf-btn-ghost px-3 sm:px-4 py-2 text-sm hidden sm:inline-flex"
                >
                  Login
                </Link>
                <Link href="/auth/signup" className="cf-btn cf-btn-primary px-4 sm:px-5 py-2.5 text-sm">
                  Get Started Free
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      <section className="max-w-5xl mx-auto px-5 sm:px-8 pt-16 sm:pt-24 pb-16 text-center">
        <div className="inline-flex items-center gap-2 bg-[var(--primary-soft)] border border-[var(--primary-border)] text-[var(--primary)] px-3.5 py-1.5 rounded-full mb-6 text-xs font-semibold uppercase tracking-wide">
          AI-Powered Career Coaching
        </div>

        <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.05] mb-6">
          Get hired faster
          <br />
          <span className="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-violet-500 bg-clip-text text-transparent">
            with AI that works
          </span>
        </h1>

        <p className="text-base sm:text-lg md:text-xl cf-secondary max-w-2xl mx-auto mb-10 leading-relaxed">
          Optimize resumes, generate cover letters, track applications, and practice interviews —
          designed as a real product, not a demo.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href={hasToken ? '/dashboard' : '/auth/signup'}
            className="cf-btn cf-btn-primary px-8 py-3.5 text-base"
          >
            {hasToken ? 'Go to Dashboard' : 'Start Free Trial'}
          </Link>
          <Link href="#features" className="cf-btn cf-btn-secondary px-8 py-3.5 text-base">
            See How It Works
          </Link>
        </div>
      </section>

      <section id="features" className="max-w-6xl mx-auto px-5 sm:px-8 pb-24">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Everything you need to land the role
          </h2>
          <p className="cf-muted mt-2 text-sm sm:text-base">
            One workspace for resumes, applications, and interview practice.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-4 sm:gap-5">
          {[
            {
              href: hasToken ? '/optimizer' : '/auth/signup',
              icon: FileText,
              title: 'Smart Resume Optimizer',
              desc: 'Tailor any resume to a job description with ATS scoring and keyword insights.',
              cta: 'Try optimizer',
            },
            {
              href: hasToken ? '/applications' : '/auth/signup',
              icon: Briefcase,
              title: 'Application Tracker',
              desc: 'Move roles through wishlist, applied, interview, offer, and rejected.',
              cta: 'Open tracker',
            },
            {
              href: hasToken ? '/interview' : '/auth/signup',
              icon: Mic,
              title: 'AI Mock Interviews',
              desc: 'Role-specific questions plus Whisper voice practice and coaching feedback.',
              cta: 'Practice now',
            },
          ].map(({ href, icon: Icon, title, desc, cta }) => (
            <Link key={title} href={href} className="cf-card cf-card-interactive p-7 group block">
              <div className="w-11 h-11 rounded-2xl bg-[var(--primary-soft)] border border-[var(--primary-border)] flex items-center justify-center text-[var(--primary)] mb-5">
                <Icon className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
              <p className="cf-muted text-sm mt-2 leading-relaxed">{desc}</p>
              <span className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--primary)] mt-5 group-hover:gap-2.5 transition-all">
                {cta} <ArrowRight className="w-4 h-4" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="border-t border-[var(--card-border)] bg-[var(--card)] py-16 sm:py-20">
        <div className="max-w-2xl mx-auto text-center px-5">
          <h2 className="text-2xl sm:text-4xl font-bold tracking-tight mb-4">Ready to stand out?</h2>
          <p className="cf-secondary mb-8 text-sm sm:text-base">
            Build a sharper application pipeline with AI that stays grounded in your experience.
          </p>
          <Link
            href={hasToken ? '/dashboard' : '/auth/signup'}
            className="cf-btn cf-btn-primary px-8 py-3.5 text-base"
          >
            Start Building Your Future
          </Link>
        </div>
      </section>
    </div>
  );
}
