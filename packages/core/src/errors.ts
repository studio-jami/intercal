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
