FROM node:22-alpine
WORKDIR /workspace
RUN corepack enable
COPY pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/admin-web/package.json apps/admin-web/package.json
RUN pnpm install --frozen-lockfile --filter admin-web
COPY apps/admin-web/ apps/admin-web/
WORKDIR /workspace/apps/admin-web
EXPOSE 3000
CMD ["pnpm", "dev", "--hostname", "0.0.0.0"]
