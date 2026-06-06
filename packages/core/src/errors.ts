/** Structured errors that map cleanly onto the contract `ApiError` and MCP tool errors. */
export class IntercalError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'IntercalError';
  }
}

export class NotFoundError extends IntercalError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('not_found', message, details);
  }
}

export class InvalidRequestError extends IntercalError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('invalid_request', message, details);
  }
}

/** Thrown by query bodies whose implementation is owned by a later plan. Honest, not a mock. */
export class NotImplementedError extends IntercalError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('not_implemented', message, details);
  }
}

/** 401 — no credential, or the credential is invalid/revoked/expired. */
export class UnauthorizedError extends IntercalError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('unauthorized', message, details);
  }
}

/** 403 — authenticated, but the key lacks the scope required for this operation. */
export class ForbiddenError extends IntercalError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('forbidden', message, details);
  }
}

/** 429 — the caller exceeded its rate-limit policy window. `details.retryAfter` is seconds. */
export class RateLimitedError extends IntercalError {
  constructor(message: string, details?: Record<string, unknown>) {
    super('rate_limited', message, details);
  }
}
