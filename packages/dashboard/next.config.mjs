/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Transpile workspace packages consumed from source.
  transpilePackages: ['@intercal/sdk', '@intercal/shared'],
};

export default nextConfig;
