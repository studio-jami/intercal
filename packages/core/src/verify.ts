/**
 * `verifyClaim` body — "is this free-text claim supported by the substrate?" (Plan 03 W6).
 *
 * DESIGN: deterministic, not LLM-synthesised — the SAME architectural choice W5 (`delta.ts`) made,
 * for the same reasons:
 *   - No LLM client exists in `packages/core`, and adding provider logic past the port boundary
 *     would violate the adapter rule (AGENTS.md "Hard rules").
 *   - The steering for this workstream PREFERS a correct, fully-cited deterministic verdict over an
 *     uncited LLM blob. Every conclusion this function returns is traceable to a real claim row and
 *     its backing source documents; there is nothing to fabricate. Optional provider-backed prose
 *     ("explain the contradiction in English") is a later seam that would sit behind `LlmPort` and
 *     may only rephrase content already grounded in these citations — it can never introduce an
 *     un-cited assertion or change the verdict.
 *
 * HOW THE VERDICT IS DERIVED (evidence match + contradiction reasoning):
 *   1. RETRIEVE: lexical full-text retrieval over `claims.normalized_text` using Postgres FTS
 *      (`plainto_tsquery` + `ts_rank`) — the same lexical leg that powers W5 hybrid search and the
 *      same substrate W5 reads. Each retrieved claim is a candidate piece of evidence. We do NOT
 *      embed here: embeddings live behind `EmbeddingsPort` in the pipeline, not in `packages/core`'s
 *      read layer, so a deterministic FTS leg keeps this provider-free and within the boundary. (A
 *      future hybrid upgrade would add the vector leg behind the port; the contract does not change.)
 *   2. CLASSIFY each candidate as SUPPORTING or CONTRADICTING the user's claim, structurally:
 *      - polarity: the user's claim and the candidate are compared for negation. If one asserts X and
 *        the other asserts not-X (negation markers differ) for overlapping content, that candidate
 *        CONTRADICTS; otherwise a lexical overlap SUPPORTS.
 *      - support STRENGTH: lexical overlap alone is NOT proof of claim-level agreement. Bag-of-words
 *        retrieval is order- and role-blind: "McCready authored the toolchain config" and "the config
 *        authored McCready" share identical tokens, and a short user claim can be a token-subset of a
 *        verbose stored claim that asserts something different. So a SUPPORTING candidate is graded:
 *          • 'strong' — near-verbatim agreement: high SYMMETRIC content-token coverage (both the user
 *            claim and the candidate cover most of each other's content tokens) AND high Jaccard. This
 *            is essentially the same claim restated; only this can yield the strongest verdict.
 *          • 'weak'   — on-topic and same-polarity but lexical-only (one is a token-subset of the
 *            other, or tokens merely co-occur). On-topic and consistent, but NOT proof of the user's
 *            exact proposition. This can never on its own produce "supported".
 *      - substrate-recorded contradictions: a candidate flagged `contradiction_status =
 *        'has_contradiction'`, or one that is the losing side of an OPEN row in `claim_contradictions`
 *        against another retrieved candidate, contributes to the contradicting set. This is the
 *        substrate's own, human/rule/model-detected contradiction signal — authoritative, not guessed.
 *   3. SCORE + VERDICT: confidence is built from evidence strength (retrieval rank × the candidate's
 *      own extraction confidence) and the AGREEMENT between supporting and contradicting mass:
 *        - STRONG support, no contradiction       → "supported"
 *        - only WEAK (lexical-only) support, no contradiction → "partially_supported" (on-topic &
 *          consistent, but not proof of the exact proposition — never over-claimed as "supported")
 *        - support AND contradiction both present → "contradicted" when contradiction dominates,
 *          else "partially_supported" (contested but net-supported)
 *        - contradiction only                     → "contradicted"
 *        - no evidence either way                 → "unverified" (NEVER invented support)
 *
 * FALSE-POSITIVE GUARD (the central correctness risk): lexical FTS overlap ≠ semantic support. A
 * claim that shares vocabulary with stored claims but asserts a DIFFERENT subject/object/value/role
 * must NOT be reported "supported". Two independent defenses hold the line:
 *   (a) `plainto_tsquery` ANDs every content lexeme, so a fabricated specific (a wrong version, an
 *       invented CVE id, a predicate word absent from the corpus) yields NO candidate at all → the
 *       claim is "unverified", never falsely supported.
 *   (b) The support-strength gate above: a candidate that merely shares vocabulary (token-subset or
 *       role-reordering) is 'weak' support and caps the verdict at "partially_supported"; "supported"
 *       requires near-verbatim claim-level agreement. Under-claiming (partially/unverified) is the
 *       safe failure mode; a false "supported" would be the substrate asserting something untrue.
 *
 * POINT-IN-TIME (`as_of_date`): evaluated against the bitemporal state as of that date. We only
 * consider claims Intercal had ALREADY RECORDED by then (transaction time: `created_at <= as_of`)
 * AND that were valid in the world at that date (valid time: `valid_from <= as_of` when set, and
 * `valid_until` open or after the date). Without `as_of_date` we verify against the current state.
 *
 * TOKEN BUDGET: the returned evidence is bounded to `token_budget` exactly like W5 — citations are
 * ranked most-relevant-first and trimmed so the response stays within budget; the verdict and
 * confidence are computed over the FULL retrieved set first (trimming the citation list never
 * changes the verdict), so a budgeted answer is bounded but never silently mis-classified.
 */
import type { components } from '@intercal/shared';
import { sql } from 'kysely';
import type { Db } from './db/client.js';
import type { ClaimsTable } from './db/types.js';

type S = components['schemas'];
type Citation = S['Citation'];
type Verdict = S['VerificationVerdict'];

export interface VerifyClaimParams {
  claim_text: string;
  as_of_date?: string;
  token_budget?: number;
}

// Token-budget bounds — identical heuristic to delta.ts so the two synthesis surfaces behave
// consistently. The verify response is citation-light (no prose body), so the budget bounds the
// number of evidence citations rather than a digest. ~4 chars/token, deterministic and provider-free.
const DEFAULT_TOKEN_BUDGET = 1500;
const MIN_TOKEN_BUDGET = 200;
const MAX_TOKEN_BUDGET = 8000;
const estimateTokens = (text: string): number => Math.ceil(text.length / 4);

function clampBudget(n: number | undefined): number {
  const v = n ?? DEFAULT_TOKEN_BUDGET;
  if (!Number.isFinite(v)) return DEFAULT_TOKEN_BUDGET;
  return Math.min(MAX_TOKEN_BUDGET, Math.max(MIN_TOKEN_BUDGET, Math.floor(v)));
}

// Candidate retrieval cap — bounds DB work; the budget bounds the response. Mirrors delta.ts (200).
const CANDIDATE_LIMIT = 50;

// A retrieved candidate must clear this normalized relevance to count as on-topic evidence at all.
// Below it the FTS match is too weak to assert support/contradiction (avoids overclaiming on a
// stray shared stop-word). Tuned against the live corpus; exposed as a constant for auditability.
const MIN_RELEVANCE = 0.02;

// ── Support-strength thresholds (the false-positive guard). ────────────────────────────────────
// A SUPPORTING candidate is 'strong' (can yield the "supported" verdict) only when it is essentially
// the SAME claim restated, not merely a claim that shares vocabulary. We require BOTH:
//   • high SYMMETRIC content-token coverage — the smaller of (user tokens covered by candidate) and
//     (candidate tokens covered by user). A symmetric floor defeats the two lexical false-positive
//     shapes that a one-sided subset check misses: a short user claim buried in a verbose candidate
//     (high user-coverage, low candidate-coverage) and a role-reordered restatement of a long claim.
//   • high Jaccard — overall agreement of the two content-token sets.
// Calibrated against the live corpus so genuine near-verbatim restatements clear the bar while
// token-subset / role-swapped claims that share vocabulary do not. Conservative by design: a true
// claim that lands just under the bar is reported "partially_supported" (safe under-claim), never a
// false "supported".
const STRONG_SUPPORT_MIN_COVERAGE = 0.85;
const STRONG_SUPPORT_MIN_JACCARD = 0.5;

/** Negation markers used for deterministic polarity comparison (whole-word, lowercased). */
const NEGATIONS = [
  'not',
  'no',
  "n't",
  'never',
  'without',
  'cannot',
  "can't",
  'fails',
  'failed',
  'unable',
  'removed',
  'deprecated',
  'disabled',
  'reverted',
];

const STOP = new Set([
  'the',
  'a',
  'an',
  'is',
  'was',
  'are',
  'were',
  'be',
  'been',
  'being',
  'to',
  'of',
  'in',
  'on',
  'for',
  'and',
  'or',
  'as',
  'at',
  'by',
  'with',
  'that',
  'this',
  'it',
  'its',
  'will',
  'has',
  'have',
  'had',
  'from',
]);

// The token charset keeps `. - _ ' \`` so identifier-shaped tokens survive intact
// (`Buffer.poolSize`, `1.96.0`, `tls.createServer`, `CVE-2026-5222`, `target.'cfg(..)'`). But those
// same characters as *boundary* punctuation are sentence noise, not part of the token: the stored
// claim "…default to 64 KiB." tokenizes `kib.` while a user's "…64 KiB" tokenizes `kib`, and a
// trailing-period mismatch like that wrongly drops a verbatim restatement below the strong-support
// bar (live-verified: an exact copy of a stored claim graded 'weak' → partially_supported instead of
// supported). So we strip the boundary-punctuation set from each token's leading/trailing edges only,
// preserving interior structure. This cannot widen the false-positive guard — it can only make two
// tokens that differ solely by edge punctuation compare equal, never merge distinct identifiers.
const trimTokenEdges = (t: string): string => t.replace(/^[.\-_'`]+/, '').replace(/[.\-_'`]+$/, '');

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9.\-_'`]+/g, ' ')
    .split(/\s+/)
    .map(trimTokenEdges)
    .filter((t) => t.length > 0);
}

function contentTokens(text: string): Set<string> {
  return new Set(tokenize(text).filter((t) => !STOP.has(t) && !NEGATIONS.includes(t)));
}

function isNegated(text: string): boolean {
  const toks = tokenize(text);
  return toks.some((t) => NEGATIONS.includes(t) || t.endsWith("n't"));
}

/** Jaccard overlap of content tokens — deterministic lexical agreement signal in [0,1]. */
function contentOverlap(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let inter = 0;
  for (const t of a) if (b.has(t)) inter++;
  const union = a.size + b.size - inter;
  return union === 0 ? 0 : inter / union;
}

/** Directional coverage: fraction of `a`'s content tokens that also appear in `b`, in [0,1]. */
function coverage(a: Set<string>, b: Set<string>): number {
  if (a.size === 0) return 0;
  let inter = 0;
  for (const t of a) if (b.has(t)) inter++;
  return inter / a.size;
}

/** A scored, classified evidence candidate (one retrieved claim). */
export interface Candidate {
  claim: ClaimsTable;
  /** Normalized FTS relevance to the user's claim text, in [0,1]. */
  relevance: number;
  /** Lexical content agreement (Jaccard) between user claim and this candidate, in [0,1]. */
  overlap: number;
  /** 'support' | 'contradict' — the deterministic classification (see module doc step 2). */
  stance: 'support' | 'contradict';
  /**
   * For a SUPPORTING candidate, how strong the agreement is (the false-positive guard, module doc
   * step 2): 'strong' = near-verbatim claim-level agreement (can yield "supported"); 'weak' =
   * on-topic & same-polarity but lexical-only (caps the verdict at "partially_supported"). Always
   * 'weak' for a contradicting candidate (the field is only consulted on the support side).
   */
  supportStrength: 'strong' | 'weak';
  /** Per-candidate evidence weight = relevance × extraction confidence, in [0,1]. */
  weight: number;
}

/** Raw row + its FTS rank, as returned by the retrieval query (rank already normalized to [0,1]). */
export interface RankedClaim {
  claim: ClaimsTable;
  relevance: number;
}

/**
 * Classify one retrieved claim as supporting or contradicting the user's claim. Pure and
 * deterministic — no model call. The substrate's own contradiction flag is authoritative; absent
 * that, polarity disagreement over overlapping content is a contradiction, agreement is support.
 *
 * `substrateContradicted` = the claim is the losing/contested side of an OPEN row in
 * `claim_contradictions`, OR carries `contradiction_status = 'has_contradiction'`. Either way the
 * substrate has independently recorded that this assertion is contested, so we surface it as
 * contradicting evidence rather than silently treating it as support.
 */
export function classify(
  userTokens: Set<string>,
  userNegated: boolean,
  ranked: RankedClaim,
  substrateContradicted: boolean,
): Candidate {
  const { claim, relevance } = ranked;
  const candTokens = contentTokens(claim.normalized_text);
  const overlap = contentOverlap(userTokens, candTokens);
  const candNegated = isNegated(claim.normalized_text);
  const polarityDisagrees = userNegated !== candNegated;

  // Stance: substrate-recorded contradiction OR a polarity flip over substantially-overlapping
  // content ⇒ contradict; otherwise the on-topic match supports. We require real content overlap
  // before letting a polarity flip flip the stance, so an unrelated negated sentence that merely
  // shares the retrieval terms is not miscounted as a contradiction.
  const stance: 'support' | 'contradict' =
    substrateContradicted || (polarityDisagrees && overlap >= 0.2) ? 'contradict' : 'support';

  // Support strength (the false-positive guard): a supporting candidate is 'strong' — i.e. allowed
  // to drive the "supported" verdict — only when it is essentially the SAME claim restated. We
  // require SYMMETRIC high coverage (the smaller of user→cand and cand→user content-token coverage)
  // AND high Jaccard. The symmetric floor defeats both lexical false-positive shapes: a short user
  // claim that is merely a token-subset of a verbose candidate (high one-way coverage, low the other
  // way), and a role-reordered restatement (same tokens, different proposition). Anything that only
  // shares vocabulary is 'weak' and can never alone yield "supported".
  const minCoverage = Math.min(coverage(userTokens, candTokens), coverage(candTokens, userTokens));
  const supportStrength: 'strong' | 'weak' =
    minCoverage >= STRONG_SUPPORT_MIN_COVERAGE && overlap >= STRONG_SUPPORT_MIN_JACCARD
      ? 'strong'
      : 'weak';

  const weight = relevance * Number(claim.extraction_confidence);
  return { claim, relevance, overlap, stance, supportStrength, weight };
}

/** Source-document provenance needed to build citations (url + publishedAt). */
export interface VerifyDocMeta {
  id: string;
  url: string | null;
  published_at: Date | null;
}

export interface AssembleVerifyInput {
  claimText: string;
  asOf?: Date;
  budget: number;
  candidates: Candidate[];
  docMeta: VerifyDocMeta[];
}

/** Build a Citation for a source document, enriched with url + publishedAt when known. */
function citation(docId: string, byId: Map<string, VerifyDocMeta>): Citation {
  const d = byId.get(docId);
  return {
    sourceDocumentId: docId,
    ...(d?.url ? { url: d.url } : {}),
    ...(d?.published_at ? { publishedAt: d.published_at.toISOString() } : {}),
  };
}

/**
 * Pure assembly of the `ClaimVerificationResponse` from classified candidates — verdict, confidence,
 * supporting/contradicting citations, token-budget trim. Separated from the DB fetch (`buildVerify`)
 * so the verdict/confidence/budget logic is unit-testable without a live database.
 *
 * The VERDICT and CONFIDENCE are computed over the FULL candidate set BEFORE the citation list is
 * trimmed to the token budget, so trimming the evidence shown never changes the classification —
 * a budgeted answer is bounded but never silently mis-verified.
 */
export function assembleVerification(input: AssembleVerifyInput): S['ClaimVerificationResponse'] {
  const { claimText, asOf, budget, candidates, docMeta } = input;
  const byId = new Map(docMeta.map((d) => [d.id, d]));

  const supporting = candidates.filter((c) => c.stance === 'support');
  const contradicting = candidates.filter((c) => c.stance === 'contradict');
  // Strong support = at least one supporting candidate with near-verbatim claim-level agreement.
  // Only strong support can yield the "supported" verdict; lexical-only ('weak') support, however
  // much of it there is, caps at "partially_supported" (the false-positive guard, module doc step 2).
  const hasStrongSupport = supporting.some((c) => c.supportStrength === 'strong');

  // ── Evidence mass: summed weights (relevance × extraction confidence) per side. ───────────────
  const supportMass = supporting.reduce((s, c) => s + c.weight, 0);
  const contradictMass = contradicting.reduce((s, c) => s + c.weight, 0);
  const totalMass = supportMass + contradictMass;

  // ── Verdict (deterministic; never overclaims on thin evidence). ───────────────────────────────
  let verdict: Verdict;
  let confidence: number;
  if (candidates.length === 0 || totalMass === 0) {
    // No on-topic evidence either way — explicit "unverified", no fabricated support.
    verdict = 'unverified';
    confidence = 0;
  } else if (contradictMass === 0) {
    // Support only. "supported" requires genuine claim-level agreement (a strong supporter); if every
    // supporter merely shares vocabulary (all 'weak'), the evidence is on-topic and consistent but
    // does NOT prove the user's exact proposition — report "partially_supported", never "supported".
    verdict = hasStrongSupport ? 'supported' : 'partially_supported';
    // Confidence scales with the strongest supporting weight (a single strong, fully-cited claim is
    // high-confidence; many weak ones are not summed past 1). Bounded to [0,1].
    confidence = Math.min(1, Math.max(...supporting.map((c) => c.weight)));
  } else if (supportMass === 0) {
    verdict = 'contradicted';
    confidence = Math.min(1, Math.max(...contradicting.map((c) => c.weight)));
  } else {
    // Both present (contested). Net direction by mass share; confidence reflects how decisive.
    const supportShare = supportMass / totalMass;
    if (supportShare >= 0.6) {
      verdict = 'partially_supported';
      confidence = Math.min(1, supportShare * Math.max(...supporting.map((c) => c.weight)));
    } else {
      verdict = 'contradicted';
      confidence = Math.min(
        1,
        (1 - supportShare) * Math.max(...contradicting.map((c) => c.weight)),
      );
    }
  }

  // ── Citations: rank each side most-decisive-first (weight, then relevance, then id for a stable
  // total order), then token-budget-trim across BOTH sides together so the whole response is
  // bounded. Each cited source document appears once per side. ──────────────────────────────────
  const rank = (a: Candidate, b: Candidate): number => {
    if (b.weight !== a.weight) return b.weight - a.weight;
    if (b.relevance !== a.relevance) return b.relevance - a.relevance;
    return a.claim.id < b.claim.id ? -1 : a.claim.id > b.claim.id ? 1 : 0;
  };
  const orderedSupport = [...supporting].sort(rank);
  const orderedContradict = [...contradicting].sort(rank);

  const supportingEvidence: Citation[] = [];
  const contradictingEvidence: Citation[] = [];
  const seenSupport = new Set<string>();
  const seenContradict = new Set<string>();
  // Reserve the fixed scalar fields (claimText + verdict + asOf) in the budget so the citation list
  // alone never pushes the response over budget. Each citation costs ~its serialized length.
  let spent = estimateTokens(claimText) + estimateTokens(verdict) + (asOf ? 8 : 0);
  const citationCost = (cit: Citation): number =>
    estimateTokens(cit.sourceDocumentId + (cit.url ?? '') + (cit.publishedAt ?? ''));

  // Interleave the two ranked sides so neither is starved when the budget is tight: take the most
  // decisive remaining citation from whichever side has the heavier next item.
  let si = 0;
  let ci = 0;
  while (si < orderedSupport.length || ci < orderedContradict.length) {
    const nextS = orderedSupport[si];
    const nextC = orderedContradict[ci];
    const takeSupport =
      nextS !== undefined && (nextC === undefined || nextS.weight >= nextC.weight);
    const cand = takeSupport ? nextS : nextC;
    if (cand === undefined) break;
    if (takeSupport) si++;
    else ci++;

    for (const docId of cand.claim.source_document_ids) {
      const seen = takeSupport ? seenSupport : seenContradict;
      if (seen.has(docId)) continue;
      const cit = citation(docId, byId);
      const cost = citationCost(cit);
      if (spent + cost > budget) {
        // Budget exhausted — stop adding citations. The verdict/confidence are already final
        // (computed over the full set above), so the trimmed citation list is lossy-but-honest,
        // never mis-verifying.
        si = orderedSupport.length;
        ci = orderedContradict.length;
        break;
      }
      spent += cost;
      seen.add(docId);
      (takeSupport ? supportingEvidence : contradictingEvidence).push(cit);
    }
  }

  return {
    claimText,
    verdict,
    confidence: { score: Number(confidence.toFixed(4)), method: 'evidence_match' },
    supportingEvidence,
    contradictingEvidence,
    ...(asOf ? { asOf: asOf.toISOString() } : {}),
  };
}

/**
 * DB-backed retrieval + classification for `verifyClaim`. Mirrors `buildDelta`: fetch the scoped,
 * point-in-time-filtered candidate set with a single FTS query, classify each, fetch the backing
 * doc provenance, then hand off to the pure assembler.
 */
export async function buildVerification(
  db: Db,
  params: VerifyClaimParams,
): Promise<S['ClaimVerificationResponse']> {
  const budget = clampBudget(params.token_budget);
  const asOf = params.as_of_date ? new Date(params.as_of_date) : undefined;
  const userTokens = contentTokens(params.claim_text);
  const userNegated = isNegated(params.claim_text);

  // ── Retrieve candidate claims by lexical FTS over normalized_text. We express the tsvector/
  // tsquery match and ts_rank via the `sql` template tag (the idiomatic Kysely way for FTS), which
  // binds the user text as a parameter — no injection, no hand-built SQL string. The `@@` match
  // hits the GIN index `idx_claims_normalized_fts`. ts_rank is normalized into [0,1] in JS below.
  // Point-in-time filters are applied as typed Kysely predicates. ───────────────────────────────
  const tsv = sql`to_tsvector('english', normalized_text)`;
  const tsq = sql`plainto_tsquery('english', ${params.claim_text})`;
  let q = db
    .selectFrom('claims')
    .selectAll()
    .select(sql<number>`ts_rank(${tsv}, ${tsq})`.as('rank'))
    .where('status', '=', 'active')
    .where(sql<boolean>`${tsv} @@ ${tsq}`);

  if (asOf) {
    // Transaction time: only what Intercal had recorded by `as_of` (created_at is the claim's
    // transaction-time axis; claims has no recorded_at — see db/types.ts).
    q = q.where('created_at', '<=', asOf);
    // World/valid time: the claim was valid at `as_of` (open intervals count).
    q = q
      .where((eb) => eb.or([eb('valid_from', 'is', null), eb('valid_from', '<=', asOf)]))
      .where((eb) => eb.or([eb('valid_until', 'is', null), eb('valid_until', '>', asOf)]));
  }

  const rows = await q.orderBy('rank', 'desc').limit(CANDIDATE_LIMIT).execute();

  // Normalize ts_rank (unbounded, typically small) into [0,1] deterministically: r/(r+1). This is
  // monotonic, keeps the ranking order, and bounds the evidence weight without a corpus-global max.
  const ranked: RankedClaim[] = rows
    .map((row) => {
      const raw = Number((row as ClaimsTable & { rank: number }).rank) || 0;
      const relevance = raw / (raw + 1);
      const { rank: _rank, ...claim } = row as ClaimsTable & { rank: number };
      return { claim: claim as ClaimsTable, relevance };
    })
    .filter((r) => r.relevance >= MIN_RELEVANCE);

  // ── Substrate-recorded contradictions among the retrieved set. A claim is "substrate-contradicted"
  // if it carries contradiction_status='has_contradiction', OR it is a party to an OPEN row in
  // claim_contradictions whose OTHER party is also in the retrieved set (a real, live conflict
  // between two on-topic claims — not a stale or resolved one). ──────────────────────────────────
  const candidateIds = ranked.map((r) => r.claim.id);
  const substrateContradicted = new Set<string>();
  for (const r of ranked) {
    if (r.claim.contradiction_status === 'has_contradiction') {
      substrateContradicted.add(r.claim.id);
    }
  }
  if (candidateIds.length > 0) {
    const conflicts = await db
      .selectFrom('claim_contradictions')
      .select(['claim_a_id', 'claim_b_id'])
      .where('resolution_status', '=', 'open')
      .where((eb) =>
        eb.or([eb('claim_a_id', 'in', candidateIds), eb('claim_b_id', 'in', candidateIds)]),
      )
      .execute();
    const idSet = new Set(candidateIds);
    for (const row of conflicts) {
      // Only count a contradiction when BOTH sides are on-topic candidates: a live conflict between
      // two retrieved claims. A conflict whose other side is off-topic is not evidence about THIS
      // claim, so it does not flip the stance.
      if (idSet.has(row.claim_a_id) && idSet.has(row.claim_b_id)) {
        substrateContradicted.add(row.claim_a_id);
        substrateContradicted.add(row.claim_b_id);
      }
    }
  }

  const candidates = ranked.map((r) =>
    classify(userTokens, userNegated, r, substrateContradicted.has(r.claim.id)),
  );

  // ── Backing source-document provenance for citations (url + publishedAt). ─────────────────────
  const docIds = new Set<string>();
  for (const c of candidates) for (const id of c.claim.source_document_ids) docIds.add(id);
  const docMeta: VerifyDocMeta[] =
    docIds.size > 0
      ? await db
          .selectFrom('source_documents')
          .select(['id', 'url', 'published_at'])
          .where('id', 'in', [...docIds])
          .execute()
      : [];

  return assembleVerification({
    claimText: params.claim_text,
    asOf,
    budget,
    candidates,
    docMeta,
  });
}
