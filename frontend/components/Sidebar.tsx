'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  FileText,
  Mic,
  User,
  LogOut
} from 'lucide-react';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/optimizer', label: 'Resume Optimizer', icon: FileText },
  { href: '/interview', label: 'Mock Interview', icon: Mic },
  { href: '/profile', label: 'Profile', icon: User },
];

interface SidebarProps {
  onClose?: () => void;
  mobileOpen?: boolean;
  children?: React.ReactNode;
}

export default function Sidebar(props: SidebarProps) {
  const pathname = usePathname();

  return (
    <div className="w-64 bg-zinc-900 border-r border-zinc-800 min-h-screen p-6">
      <div className="mb-10">
        <h1 className="text-2xl font-bold text-purple-500">CareerForge AI</h1>
        <p className="text-xs text-zinc-500">Get Hired Faster</p>
      </div>

      <nav className="space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-colors ${isActive
                  ? 'bg-purple-600 text-white'
                  : 'hover:bg-zinc-800 text-zinc-300'
                }`}
            >
              <Icon className="w-5 h-5" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="absolute bottom-6 left-6">
        <button
          onClick={() => {
            localStorage.removeItem("token");
            window.location.href = "/auth/login";
          }}
          className="flex items-center gap-3 text-red-400 hover:text-red-500"
        >
          <LogOut className="w-5 h-5" /> Logout
        </button>
      </div>
    </div>
  );
}
