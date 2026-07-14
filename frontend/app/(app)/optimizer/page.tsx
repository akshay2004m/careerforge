'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import Link from 'next/link';
import {
  Upload,
  Sparkles,
  Download,
  Copy,
  Check,
  FileText,
  Building2,
  Briefcase,
  Tags,
  Loader2,
  ArrowRight,
  BarChart3,
} from 'lucide-react';
import { api, asResumeText, type OptimizeResult, type ResumeSummary } from '@/lib/api';
import ATSScore from '@/components/ATSScore';
import { downloadTextAsPdf } from '@/lib/pdfExport';
import { PageHeader, EmptyState } from '@/components/ui';
import { normalizeAtsDisplay } from '@/lib/atsDisplay';

export default function OptimizerPage() {
  const [file, setFile] = useState<File | null>(null);
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [selectedResumeId, setSelectedResumeId] = useState<string>('');
  const [jobDesc, setJobDesc] = useState('');
  const [company, setCompany] = useState('');
  const [role, setRole] = useState('');
  const [createApp, setCreateApp] = useState(true);
  const [skills, setSkills] = useState<string[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<'resume' | 'cover' | 'tips' | 'ats'>('resume');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void api
        .listResumes()
        .then((list) => {
          setResumes(list);
          const primary = list.find((r) => r.is_primary) || list[0];
          if (primary) setSelectedResumeId(String(primary.id));
        })
        .catch(() => {});
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  const extractSkills = async () => {
    if (jobDesc.trim().length < 20) {
      toast.error('Paste a fuller job description first');
      return;
    }
    setExtracting(true);
    try {
      const data = await api.extractSkills(jobDesc);
      setSkills(data.skills);
      toast.success(`Extracted ${data.skills.length} skills`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Skill extract failed');
    } finally {
      setExtracting(false);
    }
  };

  const handleOptimize = async () => {
    if (!jobDesc.trim() || jobDesc.trim().length < 20) {
      toast.error('Paste a full job description');
      return;
    }

    setLoading(true);
    setResult(null);
    try {
      let resumeId = selectedResumeId ? Number(selectedResumeId) : 0;
      if (file) {
        const uploadData = await api.uploadResume(file, {
          title: file.name.replace(/\.pdf$/i, ''),
        });
        resumeId = uploadData.resume_id;
        const list = await api.listResumes();
        setResumes(list);
        setSelectedResumeId(String(resumeId));
      }
      if (!resumeId) {
        toast.error('Select a saved resume or upload a PDF');
        setLoading(false);
        return;
      }

      const optimizeData = await api.optimize({
        resume_id: resumeId,
        job_description: jobDesc,
        create_application: createApp,
        company: company || undefined,
        role: role || undefined,
      });
      setResult(optimizeData);
      if (optimizeData.skills?.length) setSkills(optimizeData.skills);
      setTab('resume');
      toast.success(
        optimizeData.application_id
          ? 'Optimized and saved to Applications'
          : 'Resume optimized successfully'
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Optimization failed');
    } finally {
      setLoading(false);
    }
  };

  const resumeText = asResumeText(result?.tailored_resume);
  const atsDisplay = result ? normalizeAtsDisplay(result) : null;

  const downloadText = (content: string, filename: string) => {
    const element = document.createElement('a');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    element.href = URL.createObjectURL(blob);
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    URL.revokeObjectURL(element.href);
  };

  const copyActive = async () => {
    if (!result) return;
    const text =
      tab === 'resume'
        ? resumeText
        : tab === 'cover'
          ? result.cover_letter
          : [
              'Key improvements:',
              ...(result.key_improvements || []).map((i) => `• ${i}`),
              '',
              'Missing keywords:',
              ...(result.missing_keywords || []).map((k) => `• ${k}`),
              '',
              'JD skills:',
              ...(result.skills || skills).map((k) => `• ${k}`),
            ].join('\n');
    await navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="AI · ATS · Cover letter"
        title="Resume Optimizer"
        description="Pick a saved resume or upload a new PDF, paste a job description, and get a tailored version with score and skills."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 lg:gap-6">
        {/* Input panel */}
        <div className="cf-card p-5 sm:p-6 space-y-5 cf-animate-in">
          <div>
            <label className="cf-label">Saved resume</label>
            <select
              className="cf-input px-4 py-3"
              value={selectedResumeId}
              onChange={(e) => setSelectedResumeId(e.target.value)}
            >
              <option value="">Select resume…</option>
              {resumes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title || `Resume #${r.id}`}
                  {r.is_primary ? ' ★ primary' : ''}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="cf-label">Or upload new PDF</label>
            <label
              className={`flex flex-col items-center justify-center gap-2.5 w-full min-h-[96px] border border-dashed rounded-2xl p-5 cursor-pointer transition-all duration-200 ${
                file
                  ? 'border-[var(--primary-border)] bg-[var(--primary-soft)]'
                  : 'border-[var(--card-border)] hover:border-[var(--primary-border)] hover:bg-[var(--primary-soft)]/40'
              }`}
            >
              <div className="w-10 h-10 rounded-xl bg-[var(--card)] border border-[var(--card-border)] flex items-center justify-center">
                <Upload className="w-4 h-4 text-[var(--primary)]" />
              </div>
              <span className="text-sm cf-secondary text-center">
                {file ? file.name : 'Drop or click to upload (max 10MB)'}
              </span>
              <input
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
          </div>

          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="cf-label">
                <Building2 className="w-3 h-3 inline mr-1 opacity-70" />
                Company
              </label>
              <input
                className="cf-input px-4 py-3"
                placeholder="e.g. Acme Corp"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
              />
            </div>
            <div>
              <label className="cf-label">
                <Briefcase className="w-3 h-3 inline mr-1 opacity-70" />
                Role
              </label>
              <input
                className="cf-input px-4 py-3"
                placeholder="e.g. Senior Engineer"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="cf-label">Job description</label>
            <textarea
              placeholder="Paste the full job posting here…"
              value={jobDesc}
              onChange={(e) => setJobDesc(e.target.value)}
              className="cf-input w-full h-44 p-4 resize-none"
            />
            <div className="flex flex-wrap items-center justify-between gap-2 mt-2">
              <p className="text-xs cf-muted tabular-nums">{jobDesc.length} characters</p>
              <button
                type="button"
                onClick={extractSkills}
                disabled={extracting}
                className="cf-btn cf-btn-ghost text-xs px-2 py-1 text-[var(--primary)]"
              >
                {extracting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Tags className="w-3.5 h-3.5" />
                )}
                Extract skills
              </button>
            </div>
          </div>

          {skills.length > 0 && (
            <div className="flex flex-wrap gap-1.5 cf-scale-in">
              {skills.slice(0, 20).map((s) => (
                <span key={s} className="cf-badge cf-badge-primary">
                  {s}
                </span>
              ))}
            </div>
          )}

          <label className="flex items-center gap-2.5 text-sm cursor-pointer select-none">
            <input
              type="checkbox"
              checked={createApp}
              onChange={(e) => setCreateApp(e.target.checked)}
              className="rounded border-[var(--input-border)] text-[var(--primary)] focus:ring-[var(--primary)]"
            />
            <span className="cf-secondary">Also create an application tracker entry</span>
          </label>

          <button
            onClick={handleOptimize}
            disabled={loading || !jobDesc.trim() || (!file && !selectedResumeId)}
            className="cf-btn cf-btn-primary w-full py-3.5 text-base"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Optimizing with AI…
              </>
            ) : (
              <>
                <Sparkles className="w-5 h-5" />
                Optimize resume with AI
              </>
            )}
          </button>
        </div>

        {/* Results panel */}
        <div className="cf-card p-5 sm:p-6 min-h-[420px] cf-animate-in cf-delay-2">
          {!result ? (
            <EmptyState
              icon={<Sparkles className="w-5 h-5" />}
              title="Results appear here"
              description="After optimization you’ll get a tailored resume, cover letter, ATS score, and JD skills."
            />
          ) : (
            <div className="space-y-5 cf-scale-in">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold tracking-tight">AI optimized result</h3>
                  <p className="text-xs cf-muted mt-0.5">
                    Hybrid ATS
                    {result.score_before != null && result.score_delta != null
                      ? ` · ${Math.round(result.score_before)}% → ${Math.round(result.ats_score)}% (${result.score_delta >= 0 ? '+' : ''}${result.score_delta})`
                      : ` · ${result.ats_method || 'rules'}`}
                  </p>
                </div>
                <ATSScore score={result.ats_score} size={88} label="ATS fit" />
              </div>

              <div className="flex flex-wrap gap-1.5 p-1 rounded-xl bg-[var(--background)] border border-[var(--card-border)]">
                {(['resume', 'cover', 'tips', 'ats'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`flex-1 min-w-[72px] px-2.5 py-2 rounded-lg text-xs sm:text-sm font-medium capitalize transition-all duration-200 ${
                      tab === t
                        ? 'bg-[var(--primary)] text-white shadow-md'
                        : 'cf-muted hover:text-[var(--foreground)]'
                    }`}
                  >
                    {t === 'resume'
                      ? 'Resume'
                      : t === 'cover'
                        ? 'Cover'
                        : t === 'tips'
                          ? 'Tips'
                          : 'ATS'}
                  </button>
                ))}
              </div>

              <div
                key={tab}
                className="cf-slide-in rounded-2xl border border-[var(--card-border)] bg-[var(--background)] p-4 sm:p-5 max-h-[380px] overflow-auto text-sm whitespace-pre-wrap leading-relaxed"
              >
                {tab === 'resume' && resumeText}
                {tab === 'cover' && result.cover_letter}
                {tab === 'tips' && (
                  <div className="space-y-4">
                    <div>
                      <p className="text-[var(--primary)] font-semibold mb-2 text-xs uppercase tracking-wide">
                        Key improvements
                      </p>
                      <ul className="list-disc pl-5 space-y-1.5 cf-secondary">
                        {(result.key_improvements || []).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="text-[var(--primary)] font-semibold mb-2 text-xs uppercase tracking-wide">
                        Matched keywords
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {(result.matched_keywords || []).map((k) => (
                          <span key={k} className="cf-badge cf-badge-success">
                            {k}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-[var(--primary)] font-semibold mb-2 text-xs uppercase tracking-wide">
                        Still missing
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {(result.missing_keywords || []).map((k) => (
                          <span key={k} className="cf-badge cf-badge-warning">
                            {k}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {tab === 'ats' && atsDisplay && (
                  <div className="space-y-5 whitespace-normal">
                    {/* Overall hero */}
                    <div className="flex flex-col sm:flex-row sm:items-center gap-4 rounded-2xl border border-[var(--primary-border)] bg-[var(--primary-soft)] p-4">
                      <ATSScore score={atsDisplay.overall} size={96} label="Overall ATS" />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--primary)]">
                          Overall ATS Score
                        </p>
                        <p className="text-3xl font-bold tabular-nums tracking-tight mt-1">
                          {atsDisplay.overall}
                          <span className="text-base font-medium cf-muted">/100</span>
                        </p>
                        {atsDisplay.scoreBefore != null && atsDisplay.scoreDelta != null && (
                          <p className="text-xs cf-muted mt-1">
                            Before optimize: {Math.round(atsDisplay.scoreBefore)}%
                            <span
                              className={
                                atsDisplay.scoreDelta >= 0
                                  ? ' text-[var(--success)] font-semibold'
                                  : ' text-[var(--danger)] font-semibold'
                              }
                            >
                              {' '}
                              ({atsDisplay.scoreDelta >= 0 ? '+' : ''}
                              {atsDisplay.scoreDelta} pts)
                            </span>
                          </p>
                        )}
                        <p className="text-[11px] cf-muted mt-2 leading-relaxed">
                          Hybrid engine: Rules + Semantic (Chroma) + LLM coaching — not a single
                          model guess.
                          {atsDisplay.method ? ` · ${atsDisplay.method}` : ''}
                        </p>
                      </div>
                    </div>

                    {/* Primary cards: Keyword / Structure / Relevance */}
                    <div className="grid sm:grid-cols-3 gap-3">
                      {atsDisplay.cards.map((card) => {
                        const val = card.value;
                        const color =
                          val >= 80
                            ? 'from-emerald-500 to-teal-400'
                            : val >= 60
                              ? 'from-violet-500 to-fuchsia-500'
                              : 'from-amber-500 to-orange-400';
                        return (
                          <div
                            key={card.key}
                            className="rounded-2xl border border-[var(--card-border)] p-4 cf-scale-in"
                          >
                            <p className="text-[11px] font-semibold cf-muted uppercase tracking-wide">
                              {card.label}
                            </p>
                            <p className="text-2xl font-bold tabular-nums mt-1">
                              {val}
                              <span className="text-sm font-medium cf-muted">{card.unit}</span>
                            </p>
                            <div className="h-2 mt-3 rounded-full bg-[var(--background)] border border-[var(--card-border)] overflow-hidden">
                              <div
                                className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-500`}
                                style={{ width: `${Math.min(100, val)}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Layer engine detail (secondary) */}
                    {atsDisplay.layerScores && (
                      <div>
                        <p className="text-xs font-semibold cf-muted uppercase tracking-wide mb-2 flex items-center gap-1.5">
                          <BarChart3 className="w-3.5 h-3.5" />
                          Engine layers
                        </p>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            [
                              'Rules',
                              atsDisplay.layerScores.rules,
                              atsDisplay.layerScores.rules_max ?? 55,
                            ],
                            [
                              'Semantic',
                              atsDisplay.layerScores.semantic,
                              atsDisplay.layerScores.semantic_max ?? 25,
                            ],
                            [
                              'LLM',
                              atsDisplay.layerScores.llm,
                              atsDisplay.layerScores.llm_max ?? 20,
                            ],
                          ].map(([label, score, max]) => {
                            const s = Number(score) || 0;
                            const m = Number(max) || 1;
                            return (
                              <div
                                key={String(label)}
                                className="rounded-xl border border-[var(--card-border)] bg-[var(--background)]/50 p-2.5 text-center"
                              >
                                <p className="text-[10px] uppercase tracking-wide cf-muted font-semibold">
                                  {label as string}
                                </p>
                                <p className="text-sm font-bold tabular-nums mt-0.5">
                                  {s}
                                  <span className="text-[10px] font-medium cf-muted">/{m}</span>
                                </p>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {atsDisplay.qualitativeSummary && (
                      <p className="text-sm cf-secondary leading-relaxed border-l-2 border-[var(--primary)] pl-3">
                        {atsDisplay.qualitativeSummary}
                      </p>
                    )}

                    {/* Suggestions */}
                    <div className="rounded-2xl border border-[var(--card-border)] p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--primary)] mb-2">
                        Suggestions to improve
                      </p>
                      {atsDisplay.suggestions.length === 0 ? (
                        <p className="text-sm cf-muted">No suggestions for this run.</p>
                      ) : (
                        <ul className="space-y-2">
                          {atsDisplay.suggestions.map((s) => (
                            <li key={s} className="text-sm cf-secondary leading-relaxed flex gap-2">
                              <span className="text-[var(--primary)] shrink-0">→</span>
                              <span>{s}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    {(atsDisplay.strengths || []).length > 0 && (
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide cf-muted mb-2">
                          Strengths
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {atsDisplay.strengths!.map((s) => (
                            <span key={s} className="cf-badge cf-badge-success">
                              {s}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="flex flex-wrap gap-2.5">
                <button onClick={copyActive} className="cf-btn cf-btn-secondary flex-1 min-w-[100px] py-2.5">
                  {copied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                  Copy
                </button>
                <button
                  onClick={() =>
                    downloadText(
                      tab === 'cover' ? result.cover_letter : resumeText,
                      tab === 'cover' ? 'Cover_Letter.txt' : 'Optimized_Resume.txt'
                    )
                  }
                  className="cf-btn cf-btn-secondary flex-1 min-w-[100px] py-2.5"
                >
                  <Download className="w-4 h-4" />
                  TXT
                </button>
                <button
                  onClick={() =>
                    downloadTextAsPdf(
                      tab === 'cover' ? result.cover_letter : resumeText,
                      tab === 'cover' ? 'Cover_Letter.pdf' : 'Optimized_Resume.pdf',
                      tab === 'cover' ? 'Cover Letter' : 'Optimized Resume'
                    )
                  }
                  className="cf-btn cf-btn-primary flex-1 min-w-[100px] py-2.5"
                >
                  <FileText className="w-4 h-4" />
                  PDF
                </button>
              </div>

              {/* Clear next steps after success */}
              <div className="rounded-2xl border border-[var(--primary-border)] bg-[var(--primary-soft)] p-4 space-y-2">
                <p className="text-sm font-semibold text-[var(--primary)]">Next steps</p>
                <div className="flex flex-col sm:flex-row flex-wrap gap-2">
                  {result.application_id ? (
                    <Link href="/applications" className="cf-btn cf-btn-primary text-xs px-3 py-2">
                      View in Applications <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  ) : (
                    <Link href="/applications" className="cf-btn cf-btn-secondary text-xs px-3 py-2">
                      Track this role <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  )}
                  <Link href="/interview" className="cf-btn cf-btn-secondary text-xs px-3 py-2">
                    Practice interview Qs
                  </Link>
                  <button
                    type="button"
                    onClick={() => setTab('cover')}
                    className="cf-btn cf-btn-secondary text-xs px-3 py-2"
                  >
                    Review cover letter
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
