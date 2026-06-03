/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const api = process.env.CLOVEN_API_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${api}/:path*` },
    ];
  },
};

export default nextConfig;
