# Multi-stage Next.js build using the standalone output mode.

FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund

FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY web/ ./
RUN npm run build

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN groupadd --system --gid 10001 cloven \
 && useradd --system --uid 10001 --gid cloven cloven

WORKDIR /app
COPY --from=build --chown=cloven:cloven /app/.next/standalone ./
COPY --from=build --chown=cloven:cloven /app/.next/static ./.next/static
COPY --from=build --chown=cloven:cloven /app/public ./public 2>/dev/null || true

USER cloven
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
