import { buildLlmsIndex } from '../../lib/public-docs';

export const dynamic = 'force-static';

export function GET() {
  return new Response(buildLlmsIndex(), {
    headers: {
      'content-type': 'text/plain; charset=utf-8',
    },
  });
}
