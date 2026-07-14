'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Menu } from 'lucide-react';
import Sidebar from '@/components/Sidebar';
import ProtectedRoute from '@/lib/protected';
import { getActiveNav } from '@/lib/nav';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  const active = getActiveNav(pathname);
  const ActiveIcon = active.icon;

  // Close mobile drawer when route changes (deferred to avoid sync setState-in-effect lint)
  useEffect(() => {
    const id = window.setTimeout(() => setMobileOpen(false), 0);
    return () => window.clearTimeout(id);
  }, [pathname]);

  return (
    <ProtectedRoute>
      <div className="min-h-screen flex bg-[var(--background)] text-[var(--foreground)] cf-page">
        <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />

        <div className="flex-1 min-w-0 flex flex-col min-h-screen">
          <header className="sticky top-0 z-30 border-b border-[var(--card-border)] bg-[var(--card)]/85 backdrop-blur-md">
            <div className="px-4 sm:px-6 lg:px-8 py-3 flex items-center gap-3 min-h-[56px]">
              <button
                type="button"
                onClick={() => setMobileOpen(true)}
                className="lg:hidden p-2 rounded-xl border border-[var(--card-border)] hover:bg-[var(--primary-soft)] transition-colors"
                aria-label="Open menu"
              >
                <Menu className="w-5 h-5" />
              </button>

              {/* Current page indicator */}
              <div className="flex items-center gap-2.5 min-w-0 flex-1">
                <div className="hidden sm:flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--primary-soft)] border border-[var(--primary-border)] text-[var(--primary)] shrink-0">
                  <ActiveIcon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h1 className="text-sm sm:text-base font-semibold tracking-tight truncate">
                      {active.label}
                    </h1>
                    <span className="cf-current-page">
                      <span className="cf-current-page-dot" />
                      Current page
                    </span>
                  </div>
                  <p className="text-[11px] sm:text-xs cf-muted truncate hidden xs:block sm:block">
                    {active.description}
                  </p>
                </div>
              </div>
            </div>
          </header>

          <main className="flex-1 min-w-0 overflow-auto">
            <div
              key={pathname}
              className="p-4 sm:p-6 md:p-8 lg:p-10 max-w-6xl mx-auto w-full cf-page-enter"
            >
              {children}
            </div>
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}
