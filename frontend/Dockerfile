# The web app: built with Vite, served by nginx.
# Build from the repo root, since the app imports the videos in ../examples:
#   docker build -f frontend/Dockerfile .
# VITE_* values are public and baked in at build time from frontend/.env, as with `npm run build`.
# --build-arg VITE_API_URL=https://example.com overrides the API address for production.
FROM node:22-slim AS build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY examples /app/examples
COPY frontend ./
ARG VITE_API_URL
# an empty arg would replace frontend/.env's value with nothing, so drop it when unset
RUN if [ -z "$VITE_API_URL" ]; then unset VITE_API_URL; fi && npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80
