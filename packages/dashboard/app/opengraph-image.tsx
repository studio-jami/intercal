import { ImageResponse } from 'next/og';
import { SHARE_IMAGE_ALT, SITE_NAME } from '../lib/seo';

export const alt = SHARE_IMAGE_ALT;
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function Image() {
  return new ImageResponse(
    <div
      style={{
        alignItems: 'stretch',
        background: '#f8fafc',
        color: '#111827',
        display: 'flex',
        flexDirection: 'column',
        fontFamily: 'Arial, sans-serif',
        height: '100%',
        justifyContent: 'space-between',
        padding: '68px',
        width: '100%',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 34, fontWeight: 700, letterSpacing: 0 }}>{SITE_NAME}</div>
        <div style={{ border: '2px solid #111827', borderRadius: 6, padding: '10px 14px' }}>
          MCP + REST
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ fontSize: 66, fontWeight: 700, letterSpacing: 0, lineHeight: 1.02 }}>
          Temporal knowledge for cited AI history
        </div>
        <div style={{ color: '#334155', fontSize: 30, lineHeight: 1.3, marginTop: 24 }}>
          Cutoff deltas, claim verification as of a date, provenance, freshness, and coverage.
        </div>
      </div>
      <div style={{ color: '#475569', fontSize: 24 }}>intercal.jami.studio</div>
    </div>,
    size,
  );
}
