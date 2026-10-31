# VOLT RUSH — authoritative Node/ws race server (internal compose service).
# The browser client is served statically by the FastAPI app at /kart; this
# container only runs the physics/multiplayer loop behind /kart/ws.
FROM node:22-alpine
WORKDIR /app
# Only runtime deps (ws; three is an unused client dep but harmless). No build —
# the client bundle is shipped prebuilt in ../dist and served by the portal.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY server ./server
COPY src ./src
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3108 ALLOW_CROSS_ORIGIN=true
EXPOSE 3108
# Lightweight liveness check against the server's own health endpoint.
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3108)+'/kart/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node","server/index.js"]
