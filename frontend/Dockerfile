# Imagen del frontend (Next.js), en tres etapas para que la final sea chica:
#
#   deps     instala las dependencias exactas de package-lock.json
#   build    compila la app (next build) -> carpeta .next/standalone
#   runner   solo lo necesario para correrla: sin código fuente ni herramientas
#
# Se construye desde docker compose; a mano sería:
#   docker build -t mavic-frontend --build-arg API_INTERNAL_URL=http://backend:8000 .

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
# Dirección del backend vista desde el servidor de Next (ver next.config.ts).
# Se fija al compilar: si cambia, hay que reconstruir la imagen.
ARG API_INTERNAL_URL=http://backend:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# No correr como root: la imagen de Node ya trae el usuario "node".
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
