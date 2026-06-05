/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Transpile workspace packages consumed from source.
  transpilePackages: [
    '@intercal/sdk',
    '@intercal/shared',
    '@intercal/api',
    '@intercal/core',
    '@intercal/mcp-server',
  ],
  // Keep the Postgres driver out of the bundler; load it as a Node external at runtime.
  serverExternalPackages: ['pg'],
};

export default nextConfig;
