import {
  LayoutDashboard,
  FileText,
  Mic,
  Briefcase,
  User,
  type LucideIcon,
} from 'lucide-react';

export type NavItem = {
  href: string;
  label: string;
  shortLabel: string;
  description: string;
  icon: LucideIcon;
};

export const NAV_ITEMS: NavItem[] = [
  {
    href: '/dashboard',
    label: 'Dashboard',
    shortLabel: 'Dashboard',
    description: 'Overview & analytics',
    icon: LayoutDashboard,
  },
  {
    href: '/optimizer',
    label: 'Resume Optimizer',
    shortLabel: 'Optimizer',
    description: 'ATS scoring & tailoring',
    icon: FileText,
  },
  {
    href: '/interview',
    label: 'Mock Interview',
    shortLabel: 'Interview',
    description: 'Practice with AI feedback',
    icon: Mic,
  },
  {
    href: '/applications',
    label: 'Applications',
    shortLabel: 'Apps',
    description: 'Track your pipeline',
    icon: Briefcase,
  },
  {
    href: '/profile',
    label: 'Profile',
    shortLabel: 'Profile',
    description: 'Account & resumes',
    icon: User,
  },
];

export function getActiveNav(pathname: string): NavItem {
  const match =
    NAV_ITEMS.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`)) ||
    NAV_ITEMS[0];
  return match;
}

export function isNavActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}
