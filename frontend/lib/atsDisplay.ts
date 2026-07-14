/**
 * Normalize ATS display cards for the UI.
 * Prefer backend `display_scores`; if missing (old API), derive from breakdown/layers.
 */
import type { OptimizeResult } from '@/lib/api';

export type DisplayCard = {
  key: string;
  label: string;
  value: number;
  unit: string;
};

export type NormalizedAtsDisplay = {
  overall: number;
  keywordMatch: number;
  structureFormatting: number;
  relevance: number;
  suggestions: string[];
  cards: DisplayCard[];
  scoreBefore?: number | null;
  scoreDelta?: number | null;
  qualitativeSummary?: string;
  strengths?: string[];
  layerScores?: OptimizeResult['layer_scores'];
  method?: string;
};

function clampPct(n: number) {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function pctFromScoreMax(score?: number, max?: number) {
  const s = Number(score) || 0;
  const m = Number(max) || 0;
  if (m <= 0) return 0;
  return clampPct((s / m) * 100);
}

/** Derive interview-friendly cards when API omits display_scores. */
export function normalizeAtsDisplay(result: OptimizeResult): NormalizedAtsDisplay {
  const ds = result.display_scores || {};
  const br = result.ats_breakdown || {};
  const layers = result.layer_scores || {};

  // Keyword Match %
  let keyword =
    ds.keyword_match ??
    br.keyword_coverage?.ratio ??
    br.keyword_coverage?.ratio_pct ??
    null;
  if (keyword == null) {
    keyword = pctFromScoreMax(br.keyword_coverage?.score, br.keyword_coverage?.max || 30);
  }

  // Structure & Formatting %
  let structure = ds.structure_formatting ?? null;
  if (structure == null) {
    const sec = pctFromScoreMax(br.sections?.score, br.sections?.max || 12);
    const len = pctFromScoreMax(br.length?.score, br.length?.max || 8);
    structure = clampPct(0.65 * sec + 0.35 * len);
  }

  // Relevance %
  let relevance = ds.relevance ?? null;
  if (relevance == null) {
    const semBest = br.semantic?.best_similarity;
    const semAvg = br.semantic?.avg_similarity;
    if (semBest != null || semAvg != null) {
      relevance = clampPct(0.6 * (semBest ?? 0) + 0.4 * (semAvg ?? 0));
    } else if (br.semantic?.score != null && br.semantic?.max) {
      relevance = pctFromScoreMax(br.semantic.score, br.semantic.max);
    } else if (layers.semantic != null && layers.semantic_max) {
      // blend semantic layer + keyword as proxy
      const semPct = pctFromScoreMax(layers.semantic, layers.semantic_max);
      const llmPct = pctFromScoreMax(layers.llm, layers.llm_max || 20);
      relevance = clampPct(0.55 * semPct + 0.25 * llmPct + 0.2 * Number(keyword));
    } else {
      relevance = clampPct(Number(keyword) * 0.7);
    }
  }

  const overall = clampPct(ds.overall ?? result.ats_score ?? 0);
  keyword = clampPct(Number(keyword));
  structure = clampPct(Number(structure));
  relevance = clampPct(Number(relevance));

  const cards: DisplayCard[] =
    Array.isArray(ds.cards) && ds.cards.length >= 3
      ? ds.cards.map((c) => ({
          key: c.key,
          label: c.label,
          value: clampPct(Number(c.value) || 0),
          unit: c.unit || '%',
        }))
      : [
          { key: 'keyword_match', label: 'Keyword Match', value: keyword, unit: '%' },
          {
            key: 'structure_formatting',
            label: 'Structure & Formatting',
            value: structure,
            unit: '%',
          },
          { key: 'relevance', label: 'Relevance', value: relevance, unit: '%' },
        ];

  const suggestions =
    (ds.suggestions && ds.suggestions.length ? ds.suggestions : null) ||
    result.suggestions ||
    result.key_improvements ||
    [];

  return {
    overall,
    keywordMatch: keyword,
    structureFormatting: structure,
    relevance,
    suggestions: suggestions.slice(0, 8),
    cards,
    scoreBefore: result.score_before,
    scoreDelta: result.score_delta,
    qualitativeSummary: result.qualitative_summary,
    strengths: result.strengths,
    layerScores: result.layer_scores,
    method: result.ats_method,
  };
}
