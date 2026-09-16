FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile || pnpm install
COPY apps/web apps/web
RUN pnpm --filter @rockyroad/web build

FROM caddy:2.10.0-alpine
COPY --from=build /app/apps/web/dist /srv/web
