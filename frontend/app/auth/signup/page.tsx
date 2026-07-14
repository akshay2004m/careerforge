'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { api } from '@/lib/api';

function passwordError(password: string): string | null {
  if (password.length < 8) {
    return 'Password must be at least 8 characters';
  }
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    return 'Password must include both letters and numbers (e.g. career2026)';
  }
  return null;
}

export default function Signup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const handleSignup = async (e?: FormEvent) => {
    e?.preventDefault();
    setError(null);

    const trimmedName = name.trim();
    const trimmedEmail = email.trim().toLowerCase();

    if (!trimmedName || !trimmedEmail || !password) {
      const msg = 'Please fill all fields';
      setError(msg);
      toast.error(msg);
      return;
    }

    const pwErr = passwordError(password);
    if (pwErr) {
      setError(pwErr);
      toast.error(pwErr);
      return;
    }

    setLoading(true);
    try {
      const data = await api.signup({
        name: trimmedName,
        email: trimmedEmail,
        password,
      });
      if (!data?.access_token) {
        throw new Error('Account created but no token returned. Try logging in.');
      }
      localStorage.setItem('token', data.access_token);
      toast.success('Account created');
      router.replace('/dashboard');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Signup failed';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] cf-page flex items-center justify-center px-4 py-10">
      <div className="cf-card w-full max-w-md p-8 sm:p-10 relative overflow-hidden">
        <div className="pointer-events-none absolute -top-20 -right-16 w-48 h-48 rounded-full bg-violet-500/15 blur-3xl" />
        <div className="relative text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2.5 mb-6">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center shadow-lg shadow-violet-500/20">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold tracking-tight">CareerForge AI</span>
          </Link>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Create your account</h1>
          <p className="cf-muted mt-2 text-sm">Start your AI career journey today</p>
        </div>

        <form className="relative space-y-3.5" onSubmit={handleSignup} noValidate>
          <div>
            <label className="cf-label" htmlFor="signup-name">
              Full name
            </label>
            <input
              id="signup-name"
              type="text"
              autoComplete="name"
              placeholder="Alex Rivera"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="cf-input px-4 py-3"
              disabled={loading}
              required
            />
          </div>
          <div>
            <label className="cf-label" htmlFor="signup-email">
              Email
            </label>
            <input
              id="signup-email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="cf-input px-4 py-3"
              disabled={loading}
              required
            />
          </div>
          <div>
            <label className="cf-label" htmlFor="signup-password">
              Password
            </label>
            <input
              id="signup-password"
              type="password"
              autoComplete="new-password"
              placeholder="Min 8 chars, letters + numbers"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="cf-input px-4 py-3"
              disabled={loading}
              required
              minLength={8}
            />
            <p className="text-xs cf-muted mt-1.5">
              Use at least 8 characters with letters and a number (example:{' '}
              <span className="font-medium text-[var(--foreground)]">forge2026</span>)
            </p>
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-xl border border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-300 px-3.5 py-2.5 text-sm"
            >
              {error}
              {error.toLowerCase().includes('already registered') && (
                <>
                  {' '}
                  <Link href="/auth/login" className="underline font-medium">
                    Log in
                  </Link>
                </>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="cf-btn cf-btn-primary w-full mt-2 py-3.5 text-base"
          >
            {loading ? 'Creating your account...' : 'Create Account'}
          </button>
        </form>

        <p className="text-center mt-6 text-sm cf-muted">
          Already have an account?{' '}
          <Link href="/auth/login" className="text-[var(--primary)] font-medium hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
