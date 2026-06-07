import { IntercalApiError } from '@intercal/sdk';
import { describe, expect, it } from 'vitest';
import { citationLabel, safeCitationHref } from './citations';
import { compactId, describeError, formatPercent } from './format';

describe('dashboard format helpers', () => {
  it('formats unknown percentages explicitly', () => {
    expect(formatPercent(undefined)).toBe('unknown');
    expect(formatPercent(0.734)).toBe('73%');
  });

  it('preserves API error taxonomy in user-facing messages', () => {
    const err = new IntercalApiError(404, 'not_found', 'No entity found');
    expect(describeError(err)).toBe('not_found: No entity found');
  });

  it('compacts long ids without hiding both ends', () => {
    expect(compactId('12345678-1234-1234-1234-abcdefabcdef')).toBe('12345678...abcdef');
  });

  it('only renders http and https citation URLs as outbound links', () => {
    const id = '12345678-1234-1234-1234-abcdefabcdef';

    expect(safeCitationHref('https://example.com/path')).toBe('https://example.com/path');
    expect(safeCitationHref('http://example.com/path')).toBe('http://example.com/path');
    expect(safeCitationHref('javascript:alert(1)')).toBeUndefined();
    expect(safeCitationHref('mailto:source@example.com')).toBeUndefined();
    expect(safeCitationHref('/source/local-record')).toBeUndefined();
    expect(safeCitationHref('not a url')).toBeUndefined();
    expect(citationLabel('javascript:alert(1)', id)).toBe('12345678...abcdef');
  });
});
