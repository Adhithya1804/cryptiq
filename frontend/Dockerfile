# syntax=docker/dockerfile:1.7

########################################################################
# Stage 1 — build the production bundle with Vite.
########################################################################
FROM node:20-alpine AS builder

WORKDIR /app

# Deterministic install from the committed lockfile.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# The API base URL is baked into the bundle at build time. It must be an
# absolute URL (the app's URL builder requires it). Override for your
# deployment, e.g.:
#   --build-arg VITE_API_BASE_URL=https://api.example.com/api/v1
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ARG VITE_API_TIMEOUT_MS=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS

RUN npm run build

########################################################################
# Stage 2 — serve the static bundle from a non-root nginx.
########################################################################
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

# Image already runs as uid 101 (nginx) and listens on 8080.
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder --chown=nginx:nginx /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=4s --start-period=5s --retries=3 \
    CMD ["/bin/sh", "-c", "wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1"]
