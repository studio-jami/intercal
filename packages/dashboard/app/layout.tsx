import type { ReactNode } from 'react';
import './globals.css';

export const metadata = {
  title: 'Intercal',
  description: 'An open, provenance-backed temporal knowledge substrate for agents.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="mx-auto max-w-4xl px-6 py-10">{children}</body>
    </html>
  );
}
