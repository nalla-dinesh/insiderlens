# InsiderLens web — static build served by nginx (Phase 08).
# Stage 1: vite build (node:20-alpine) → dist/
# Stage 2: nginx:alpine serves dist + proxies /api (nginx.conf is hand-written).
FROM node:20-alpine AS builder
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci
COPY apps/web/ ./
# Browser hits SAME-origin /api — nginx proxies to the api service.
ENV VITE_API_URL=
RUN npm run build

FROM nginx:1.27-alpine AS final
COPY --from=builder /web/dist /usr/share/nginx/html
COPY infra/nginx/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
CMD ["nginx", "-g", "daemon off;"]
