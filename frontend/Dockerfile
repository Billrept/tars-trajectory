FROM oven/bun:1.4.2 AS build
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
ARG PUBLIC_API_URL=http://localhost:8000
ARG PUBLIC_EPHEMERIS_URL=$PUBLIC_API_URL
ARG PUBLIC_JOBS_URL=$PUBLIC_API_URL
RUN PUBLIC_API_URL=$PUBLIC_API_URL PUBLIC_EPHEMERIS_URL=$PUBLIC_EPHEMERIS_URL PUBLIC_JOBS_URL=$PUBLIC_JOBS_URL bun run build

FROM oven/bun:1.4.2-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=bun:bun /app/node_modules ./node_modules
COPY --from=build --chown=bun:bun /app/dist ./dist
COPY --from=build --chown=bun:bun /app/package.json /app/server.ts ./
USER bun
EXPOSE 3000
CMD ["bun", "server.ts"]
