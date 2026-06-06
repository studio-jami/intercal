/**
 * Source-policy enforcement unit tests (Plan 04 W2).
 *
 * `bodySnippetAllowed` is the gate the evidence-response assembler uses before emitting any
 * derived body snippet. A snippet is a summary of the source body, so the substrate may only
 * emit one when the source permits BOTH citation of its body AND derived summaries. These tests
 * pin the truth table so a future change to the response layer cannot silently start exposing
 * restricted source text.
 */
import { describe, expect, it } from 'vitest';
import { bodySnippetAllowed } from './queries.js';

describe('bodySnippetAllowed — source policy gate', () => {
  it('allows a body snippet for a fully-permissive source', () => {
    expect(bodySnippetAllowed({ citation_only: false, summary_allowed: true })).toBe(true);
  });

  it('forbids a body snippet for a citation_only source (cite URL/title only)', () => {
    // citation_only dominates regardless of summary_allowed.
    expect(bodySnippetAllowed({ citation_only: true, summary_allowed: true })).toBe(false);
    expect(bodySnippetAllowed({ citation_only: true, summary_allowed: false })).toBe(false);
  });

  it('forbids a body snippet when summaries are not allowed, even if citable', () => {
    // A source can permit citation yet forbid derived summaries — the snippet is a summary.
    expect(bodySnippetAllowed({ citation_only: false, summary_allowed: false })).toBe(false);
  });
});
