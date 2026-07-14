'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  Star,
  Trash2,
  Upload,
  User as UserIcon,
  Lock,
  FileStack,
  LogOut,
  Loader2,
} from 'lucide-react';
import {
  api,
  clearAuth,
  type ResumeSummary,
  type UserProfile,
} from '@/lib/api';
import { PageHeader, EmptyState, SectionCard } from '@/components/ui';
import ConfirmModal from '@/components/ConfirmModal';

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [changingPw, setChangingPw] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [name, setName] = useState('');
  const [headline, setHeadline] = useState('');
  const [location, setLocation] = useState('');
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [resumeTitle, setResumeTitle] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [me, list] = await Promise.all([api.me(), api.listResumes()]);
      setUser(me);
      setName(me.name || '');
      setHeadline(me.headline || '');
      setLocation(me.location || '');
      setResumes(list);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load profile');
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

  const saveProfile = async () => {
    setSaving(true);
    try {
      const updated = await api.updateProfile({ name, headline, location });
      setUser(updated);
      toast.success('Profile updated');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Update failed');
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async () => {
    if (newPw.length < 8) {
      toast.error('New password must be at least 8 characters');
      return;
    }
    setChangingPw(true);
    try {
      await api.changePassword({ current_password: currentPw, new_password: newPw });
      setCurrentPw('');
      setNewPw('');
      toast.success('Password changed');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Password change failed');
    } finally {
      setChangingPw(false);
    }
  };

  const uploadResume = async () => {
    if (!file) {
      toast.error('Choose a PDF first');
      return;
    }
    setUploading(true);
    try {
      await api.uploadResume(file, {
        title: resumeTitle || file.name,
        set_primary: resumes.length === 0,
      });
      setFile(null);
      setResumeTitle('');
      toast.success('Resume uploaded');
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const setPrimary = async (id: number) => {
    try {
      await api.updateResume(id, { is_primary: true });
      toast.success('Primary resume updated');
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed');
    }
  };

  const rename = async (id: number, title: string) => {
    try {
      await api.updateResume(id, { title });
      toast.success('Renamed');
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Rename failed');
    }
  };

  const remove = async (id: number) => {
    setDeleting(true);
    try {
      await api.deleteResume(id);
      toast.success('Resume deleted');
      setDeleteId(null);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4 max-w-3xl">
        <div className="cf-skeleton h-20 w-2/3" />
        <div className="cf-skeleton h-48" />
        <div className="cf-skeleton h-40" />
      </div>
    );
  }

  const initials = (user?.name || user?.email || '?')
    .split(' ')
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="space-y-6 max-w-3xl">
      <PageHeader
        eyebrow="Account · Security · Resumes"
        title="Profile & settings"
        description="Manage your identity, password, and resume versions used by the optimizer."
      />

      {/* Identity card */}
      <SectionCard
        title="Your profile"
        icon={<UserIcon className="w-4 h-4 text-[var(--primary)]" />}
        className="cf-animate-in"
      >
        <div className="flex items-center gap-4 mb-5">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center text-xl font-bold text-white shadow-lg shadow-violet-500/25">
            {initials}
          </div>
          <div className="min-w-0">
            <p className="text-lg font-semibold truncate">{user?.name}</p>
            <p className="cf-muted text-sm truncate">{user?.email}</p>
            {user?.headline && (
              <p className="text-xs text-[var(--primary)] mt-1 font-medium truncate">
                {user.headline}
              </p>
            )}
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          <div>
            <label className="cf-label">Full name</label>
            <input
              className="cf-input px-4 py-3"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="cf-label">Location</label>
            <input
              className="cf-input px-4 py-3"
              placeholder="City, Country"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="cf-label">Headline</label>
            <input
              className="cf-input px-4 py-3"
              placeholder="e.g. Senior Software Engineer"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
            />
          </div>
        </div>
        <button
          onClick={saveProfile}
          disabled={saving}
          className="cf-btn cf-btn-primary mt-4 px-5 py-2.5 text-sm"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          {saving ? 'Saving…' : 'Save profile'}
        </button>
      </SectionCard>

      <SectionCard
        title="Security"
        icon={<Lock className="w-4 h-4 text-[var(--primary)]" />}
        className="cf-animate-in cf-delay-1"
      >
        <div className="grid sm:grid-cols-2 gap-3">
          <div>
            <label className="cf-label">Current password</label>
            <input
              type="password"
              className="cf-input px-4 py-3"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
            />
          </div>
          <div>
            <label className="cf-label">New password</label>
            <input
              type="password"
              className="cf-input px-4 py-3"
              placeholder="Min 8 chars, letters + numbers"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
            />
          </div>
        </div>
        <button
          onClick={changePassword}
          disabled={changingPw}
          className="cf-btn cf-btn-secondary mt-4 px-5 py-2.5 text-sm"
        >
          {changingPw ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          Update password
        </button>
      </SectionCard>

      <SectionCard
        title="Resume versions"
        icon={<FileStack className="w-4 h-4 text-[var(--primary)]" />}
        className="cf-animate-in cf-delay-2"
      >
        <p className="text-sm cf-muted mb-4">
          Upload multiple PDFs, rename them, and mark one as primary for the optimizer.
        </p>

        <div className="grid sm:grid-cols-[1fr_auto] gap-3 mb-3">
          <div>
            <label className="cf-label">Title</label>
            <input
              className="cf-input px-4 py-3"
              placeholder="e.g. Backend-focused resume"
              value={resumeTitle}
              onChange={(e) => setResumeTitle(e.target.value)}
            />
          </div>
          <div>
            <label className="cf-label">File</label>
            <label className="cf-input px-4 py-3 flex items-center gap-2 cursor-pointer min-h-[46px]">
              <Upload className="w-4 h-4 text-[var(--primary)] shrink-0" />
              <span className="text-sm truncate">{file ? file.name : 'Choose PDF'}</span>
              <input
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
          </div>
        </div>
        <button
          onClick={uploadResume}
          disabled={uploading}
          className="cf-btn cf-btn-primary px-5 py-2.5 text-sm mb-5"
        >
          {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          Upload resume
        </button>

        {resumes.length === 0 ? (
          <EmptyState
            icon={<FileStack className="w-5 h-5" />}
            title="No resumes yet"
            description="Upload a PDF to start optimizing against job descriptions."
          />
        ) : (
          <div className="space-y-2.5">
            {resumes.map((r, i) => (
              <div
                key={r.id}
                className="rounded-2xl border border-[var(--card-border)] bg-[var(--background)]/40 p-4 space-y-2 cf-scale-in"
                style={{ animationDelay: `${i * 0.04}s` }}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <p className="font-medium truncate">{r.title || `Resume #${r.id}`}</p>
                    {r.is_primary && (
                      <span className="cf-badge cf-badge-primary shrink-0">
                        <Star className="w-3 h-3" /> Primary
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {!r.is_primary && (
                      <button
                        onClick={() => setPrimary(r.id)}
                        className="cf-btn cf-btn-ghost text-xs px-2 py-1 border border-[var(--card-border)]"
                      >
                        Make primary
                      </button>
                    )}
                    <button
                      onClick={() => {
                        const t = window.prompt('New title', r.title || '');
                        if (t) void rename(r.id, t);
                      }}
                      className="cf-btn cf-btn-ghost text-xs px-2 py-1 border border-[var(--card-border)]"
                    >
                      Rename
                    </button>
                    <button
                      onClick={() => setDeleteId(r.id)}
                      className="p-1.5 rounded-lg text-[var(--danger)] hover:bg-[var(--danger-soft)] transition-colors"
                      aria-label="Delete resume"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                {r.preview && <p className="text-xs cf-muted line-clamp-2 leading-relaxed">{r.preview}</p>}
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      <button
        onClick={() => {
          clearAuth();
          router.push('/auth/login');
        }}
        className="cf-btn cf-btn-ghost text-sm text-[var(--danger)] hover:bg-[var(--danger-soft)] px-3 py-2"
      >
        <LogOut className="w-4 h-4" />
        Log out of this account
      </button>

      <ConfirmModal
        open={deleteId != null}
        title="Delete this resume?"
        description="This removes the file and its vector index chunks. Tailored history linked to it may be affected."
        confirmLabel="Delete"
        danger
        loading={deleting}
        onCancel={() => setDeleteId(null)}
        onConfirm={() => {
          if (deleteId != null) void remove(deleteId);
        }}
      />
    </div>
  );
}
