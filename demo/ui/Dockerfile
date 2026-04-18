# demo-ui — iyziops permanent demo
# Next.js 14 standalone output, non-root, PSA restricted-compatible.

FROM node:20-alpine AS deps
WORKDIR /build
COPY package.json ./
RUN npm install --no-audit --no-fund

FROM node:20-alpine AS builder
WORKDIR /build
COPY --from=deps /build/node_modules ./node_modules
COPY . .
# Build-time API URL — iyziops env_vars supports ARG injection via Dockerfile.
ARG NEXT_PUBLIC_API_URL=https://demo-api.iyziops.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine AS runner
RUN adduser -u 10001 -D -s /bin/sh app
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=builder /build/public ./public
COPY --from=builder --chown=10001:10001 /build/.next/standalone ./
COPY --from=builder --chown=10001:10001 /build/.next/static ./.next/static
USER 10001
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/',r=>process.exit(r.statusCode===200?0:1))"
CMD ["node", "server.js"]
