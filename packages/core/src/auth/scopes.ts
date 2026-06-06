/**
 * Scope vocabulary for API keys.
 *
 * The V1 surface is a PUBLIC READ substrate (AGENTS.md / Plan 04 W1): every `/v1/*` operation is a
 * read. Anonymous callers may read under a tight rate limit; a key raises the limit and is the
 * identity that future write/operator surfaces (feedback submission, subscriptions, admin) will
 * gate on. The read scopes below already exist so keys can be issued scoped-down from day one and
 * so the middleware enforces a real authorization decision, not a rubber stamp.
 */
export const SCOPES = {
  /** Read canonical knowledge: entity/delta/evidence/verify/sources/freshness reads. */
  READ: 'read',
  /** Submit feedback / report issues (Plan 04 W4 surface; reserved). */
  SUBMIT_FEEDBACK: 'submit:feedback',
  /** Manage subscriptions (Plan 04 W5 surface; reserved). */
  MANAGE_SUBSCRIPTIONS: 'manage:subscriptions',
  /** Operator administration (key issuance, overrides). Never granted to public callers. */
  ADMIN: 'admin',
} as const;

export type Scope = (typeof SCOPES)[keyof typeof SCOPES];

/** Every `/v1/*` read operation requires this scope when a key is presented. */
export const READ_SCOPE = SCOPES.READ;

/**
 * Does `granted` satisfy `required`? `admin` is a superscope (implies all). Exact match otherwise.
 * Scopes are stored as a jsonb string[]; callers pass the parsed array.
 */
export function hasScope(granted: readonly string[], required: string): boolean {
  return granted.includes(SCOPES.ADMIN) || granted.includes(required);
}
