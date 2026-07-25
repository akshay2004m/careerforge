'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  MessageSquare,
  Sparkles,
  Loader2,
  BookOpen,
  Target,
  Mic,
  MicOff,
  Square,
} from 'lucide-react';
import { api } from '@/lib/api';
import { PageHeader, SectionCard } from '@/components/ui';
import { startWhisperStream, type WhisperStreamSession } from '@/lib/whisperStream';

export default function InterviewPage() {
  const [jobDesc, setJobDesc] = useState('');
  const [questions, setQuestions] = useState<string[]>([]);
  const [commonQs, setCommonQs] = useState<string[]>([]);
  const [roleQs, setRoleQs] = useState<string[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [answer, setAnswer] = useState('');
  const [partial, setPartial] = useState('');
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [loadingFeedback, setLoadingFeedback] = useState(false);
  const [listening, setListening] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [sttHint, setSttHint] = useState('');
  const [feedback, setFeedback] = useState<{
    feedback: string;
    score: number;
    strengths: string[];
    improvements: string[];
  } | null>(null);

  const answerRef = useRef('');
  const committedRef = useRef(''); // finalized text accumulated this session
  const sessionRef = useRef<WhisperStreamSession | null>(null);
  const levelTimerRef = useRef<number | null>(null);

  useEffect(() => {
    answerRef.current = answer;
  }, [answer]);

  useEffect(() => {
    return () => {
      sessionRef.current?.abort();
      if (levelTimerRef.current) window.clearInterval(levelTimerRef.current);
    };
  }, []);

  const loadQuestions = async () => {
    if (jobDesc.trim().length < 20) {
      toast.error('Paste a fuller job description first');
      return;
    }
    setLoadingQuestions(true);
    setFeedback(null);
    setAnswer('');
    setPartial('');
    try {
      const data = await api.interviewQuestions({
        job_description: jobDesc,
        count: 8,
        include_common: true,
      });
      setQuestions(data.questions || []);
      setCommonQs(data.common || []);
      setRoleQs(data.role_specific || []);
      setActiveIndex(0);
      toast.success('Question bank ready');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to load questions');
    } finally {
      setLoadingQuestions(false);
    }
  };

  const submitAnswer = async () => {
    const transcript = answerRef.current.trim() || answer.trim();
    if (!transcript) {
      toast.error('Write or speak an answer first');
      return;
    }

    setLoadingFeedback(true);
    try {
      const data = await api.interviewFeedback({
        job_description: jobDesc || 'General professional interview',
        transcript,
      });
      setFeedback(data);
      toast.success('Feedback ready');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to get feedback');
    } finally {
      setLoadingFeedback(false);
    }
  };

  /**
   * Server now sends the *full rolling transcript* of the current utterance
   * (not tiny segment deltas). Live text replaces prior live text; only
   * text from before "Start voice" is kept as prefix (committedRef).
   */
  const mergeDisplay = useCallback((committed: string, livePartial: string) => {
    const base = committed.trim();
    const live = livePartial.trim();
    if (!base) return live;
    if (!live) return base;
    // Full re-decode already includes everything spoken this session
    if (live.toLowerCase().startsWith(base.toLowerCase())) {
      return live;
    }
    return `${base} ${live}`.replace(/\s+/g, ' ').trim();
  }, []);

  const startListening = async () => {
    if (listening || connecting) return;
    setConnecting(true);
    setPartial('');
    setSttHint('Connecting to speech engine…');
    committedRef.current = answerRef.current.trim();

    try {
      const session = await startWhisperStream({
        onReady: (info) => {
          const model = typeof info.model === 'string' ? info.model : 'Sarvam AI';
          setSttHint(`Listening · ${model}`);
          toast.success('Microphone live — start speaking');
        },
        onPartial: (text, full) => {
          // full_text = complete utterance so far (replace, don't stack fragments)
          const live = (full || text).trim();
          setPartial(live);
          const display = mergeDisplay(committedRef.current, live);
          setAnswer(display);
          answerRef.current = display;
        },
        onFinal: (text, full) => {
          // Server finalize returns the full cleaned answer for this session
          const finalPiece = (full || text).trim();
          if (finalPiece) {
            // Prefix only text that existed before Start voice (committedRef at start)
            // Final already includes the full spoken answer — do not stack partials again
            const prefix = committedRef.current.trim();
            const next =
              prefix && !finalPiece.toLowerCase().startsWith(prefix.toLowerCase())
                ? `${prefix} ${finalPiece}`.replace(/\s+/g, ' ').trim()
                : finalPiece;
            committedRef.current = next;
            setAnswer(next);
            answerRef.current = next;
          }
          setPartial('');
        },
        onError: (message) => {
          toast.error(message);
          setSttHint(message);
        },
        onLevel: (rms) => setMicLevel(rms),
      });

      sessionRef.current = session;
      setListening(true);
      setConnecting(false);

      // Poll level for UI meter even if callback gaps
      levelTimerRef.current = window.setInterval(() => {
        setMicLevel(session.getLevel());
      }, 80);
    } catch (err) {
      setConnecting(false);
      setListening(false);
      setSttHint('');
      toast.error(err instanceof Error ? err.message : 'Could not start microphone');
    }
  };

  const stopListening = async () => {
    const session = sessionRef.current;
    if (!session) {
      setListening(false);
      return;
    }
    setSttHint('Finalizing transcript…');
    try {
      const final = await session.stop();
      // onFinal handler already applied the cleaned full transcript when present
      if (final.trim()) {
        const next = answerRef.current.trim() || final.trim();
        committedRef.current = next;
        setAnswer(next);
        answerRef.current = next;
      }
      toast.success('Transcription complete');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to finalize');
    } finally {
      sessionRef.current = null;
      setListening(false);
      setConnecting(false);
      setPartial('');
      setSttHint('');
      setMicLevel(0);
      if (levelTimerRef.current) {
        window.clearInterval(levelTimerRef.current);
        levelTimerRef.current = null;
      }
    }
  };

  const currentQuestion =
    questions[activeIndex] ||
    'Tell me about yourself and why you are a strong fit for this role.';

  const wordCount = answer.trim().split(/\s+/).filter(Boolean).length;
  const levelPct = Math.min(100, Math.round(micLevel * 400));

  return (
    <div className="space-y-6 max-w-4xl">
      <PageHeader
        eyebrow="Sarvam AI · Live voice · Coaching"
        title="AI Mock Interview"
        description="Generate common + role-specific questions, answer by voice or text, then get structured feedback."
      />

      <SectionCard title="1 · Job context" icon={<Target className="w-4 h-4 text-[var(--primary)]" />} className="cf-animate-in">
        <label className="cf-label">Target job description</label>
        <textarea
          value={jobDesc}
          onChange={(e) => setJobDesc(e.target.value)}
          placeholder="Paste the job description to generate tailored interview questions…"
          className="cf-input w-full h-32 p-4 resize-none"
        />
        <button
          onClick={loadQuestions}
          disabled={loadingQuestions}
          className="cf-btn cf-btn-primary mt-4 px-5 py-2.5 text-sm"
        >
          {loadingQuestions ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {loadingQuestions ? 'Generating…' : 'Generate question bank'}
        </button>
      </SectionCard>

      <SectionCard
        title="2 · Practice"
        icon={<MessageSquare className="w-4 h-4 text-[var(--primary)]" />}
        className="cf-animate-in cf-delay-1"
      >
        {(commonQs.length > 0 || roleQs.length > 0) && (
          <div className="grid sm:grid-cols-2 gap-3 mb-5 cf-scale-in">
            <div className="rounded-2xl border border-[var(--card-border)] bg-[var(--background)]/50 p-4">
              <p className="text-xs font-semibold text-[var(--primary)] mb-2 flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5" /> Common bank
              </p>
              <ul className="space-y-1.5 text-xs cf-secondary">
                {commonQs.map((q) => (
                  <li key={q} className="line-clamp-2 leading-relaxed">
                    • {q}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-2xl border border-[var(--card-border)] bg-[var(--background)]/50 p-4">
              <p className="text-xs font-semibold text-[var(--primary)] mb-2 flex items-center gap-1.5">
                <Target className="w-3.5 h-3.5" /> Role-specific
              </p>
              <ul className="space-y-1.5 text-xs cf-secondary">
                {roleQs.slice(0, 5).map((q) => (
                  <li key={q} className="line-clamp-2 leading-relaxed">
                    • {q}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-2 mb-4">
          {(questions.length ? questions : [currentQuestion]).map((q, i) => (
            <button
              key={`${i}-${q.slice(0, 12)}`}
              onClick={() => {
                setActiveIndex(i);
                setFeedback(null);
              }}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-200 ${
                activeIndex === i
                  ? 'bg-[var(--primary)] text-white shadow-md shadow-violet-500/25 scale-105'
                  : 'border border-[var(--card-border)] cf-muted hover:border-[var(--primary-border)]'
              }`}
            >
              Q{i + 1}
            </button>
          ))}
        </div>

        <div
          key={activeIndex}
          className="cf-slide-in rounded-2xl border border-[var(--primary-border)] bg-[var(--primary-soft)] p-5 mb-6"
        >
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--primary)] mb-2">
            Current question
          </p>
          <p className="text-base sm:text-lg font-medium leading-relaxed">{currentQuestion}</p>
        </div>

        {/* Voice controls */}
        <div className="mb-4 rounded-2xl border border-[var(--card-border)] bg-[var(--background)]/40 p-4">
          <div className="flex flex-wrap items-center gap-3">
            {!listening ? (
              <button
                type="button"
                onClick={() => void startListening()}
                disabled={connecting || loadingFeedback}
                className="cf-btn cf-btn-primary px-4 py-2.5 text-sm"
              >
                {connecting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Mic className="w-4 h-4" />
                )}
                {connecting ? 'Connecting…' : 'Start voice answer'}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void stopListening()}
                className="cf-btn cf-btn-secondary px-4 py-2.5 text-sm border-red-300 text-red-600"
              >
                <Square className="w-4 h-4 fill-current" />
                Stop &amp; finalize
              </button>
            )}

            <div className="flex-1 min-w-[120px]">
              <div className="h-2 rounded-full bg-[var(--card-border)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-[var(--primary)] transition-all duration-75"
                  style={{ width: `${listening ? Math.max(levelPct, 4) : 0}%` }}
                />
              </div>
              <p className="text-[11px] cf-muted mt-1.5 flex items-center gap-1.5">
                {listening ? (
                  <>
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                    {sttHint || 'Listening…'}
                    {partial ? ' · live caption updating' : ''}
                  </>
                ) : (
                  <>
                    <MicOff className="w-3 h-3" />
                    {sttHint || 'Voice uses Sarvam AI over WebSocket (PCM 16 kHz)'}
                  </>
                )}
              </p>
            </div>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between gap-3 mb-2">
            <label className="cf-label mb-0">Your answer</label>
            <span className="text-xs cf-muted">
              {wordCount} words
              {listening && partial ? ' · partial' : ''}
            </span>
          </div>
          <textarea
            value={answer}
            onChange={(e) => {
              if (listening) return; // avoid fighting live captions
              setAnswer(e.target.value);
              answerRef.current = e.target.value;
              committedRef.current = e.target.value;
            }}
            readOnly={listening}
            placeholder="Type here, or use Start voice answer for live transcription…"
            className="cf-input w-full h-40 p-4 resize-none transition-all duration-200"
          />
          {listening && partial && (
            <p className="mt-2 text-xs text-[var(--primary)] italic line-clamp-2">
              Live: {partial}
            </p>
          )}
        </div>

        <button
          onClick={() => void submitAnswer()}
          disabled={loadingFeedback || !answer.trim() || listening}
          className="cf-btn cf-btn-primary w-full mt-4 py-3.5"
        >
          {loadingFeedback ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <MessageSquare className="w-4 h-4" />
          )}
          {loadingFeedback ? 'Analyzing answer…' : 'Get AI feedback'}
        </button>

        {feedback && (
          <div className="space-y-4 mt-6 cf-scale-in">
            <div className="rounded-2xl border border-[var(--primary-border)] bg-[var(--primary-soft)] p-5 sm:p-6">
              <div className="flex items-center justify-between gap-4 mb-3">
                <h3 className="font-semibold text-[var(--primary)]">AI feedback</h3>
                <span className="cf-badge cf-badge-success text-sm px-3 py-1">
                  {feedback.score}/10
                </span>
              </div>
              <p className="leading-relaxed text-sm sm:text-base">{feedback.feedback}</p>
            </div>

            <div className="grid md:grid-cols-2 gap-3">
              <div className="rounded-2xl border border-[var(--card-border)] p-4">
                <p className="text-sm font-semibold text-[var(--success)] mb-2">Strengths</p>
                <ul className="list-disc pl-5 text-sm cf-secondary space-y-1">
                  {feedback.strengths.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-2xl border border-[var(--card-border)] p-4">
                <p className="text-sm font-semibold text-[var(--warning)] mb-2">Improvements</p>
                <ul className="list-disc pl-5 text-sm cf-secondary space-y-1">
                  {feedback.improvements.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
