'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

type Theme = 'dark' | 'light';

const ThemeContext = createContext<{
  theme: Theme;
  toggle: () => void;
  isAnimating: boolean;
}>({ theme: 'dark', toggle: () => {}, isAnimating: false });

function applyThemeClass(next: Theme) {
  const root = document.documentElement;
  root.classList.toggle('dark', next === 'dark');
  root.classList.toggle('light', next === 'light');
  root.style.colorScheme = next;
  localStorage.setItem('cf-theme', next);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>('dark');
  const [isAnimating, setIsAnimating] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => {
      const saved = localStorage.getItem('cf-theme') as Theme | null;
      if (saved === 'light' || saved === 'dark') {
        setTheme(saved);
        applyThemeClass(saved);
      } else {
        applyThemeClass('dark');
      }
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  useEffect(() => {
    applyThemeClass(theme);
  }, [theme]);

  const toggle = useCallback(() => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    setIsAnimating(true);
    document.documentElement.classList.add('theme-transitioning');

    const run = () => setTheme(next);

    // Smooth cross-fade when supported (Chrome / Edge)
    const doc = document as Document & {
      startViewTransition?: (cb: () => void) => { finished: Promise<void> };
    };

    if (typeof doc.startViewTransition === 'function') {
      const vt = doc.startViewTransition(run);
      void vt.finished.finally(() => {
        window.setTimeout(() => {
          document.documentElement.classList.remove('theme-transitioning');
          setIsAnimating(false);
        }, 80);
      });
    } else {
      run();
      window.setTimeout(() => {
        document.documentElement.classList.remove('theme-transitioning');
        setIsAnimating(false);
      }, 420);
    }
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, toggle, isAnimating }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
