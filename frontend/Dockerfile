# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS dependencies

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM dependencies AS build

COPY . .
ENV NODE_ENV=production
RUN npm run build

FROM node:22-bookworm-slim AS runtime

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app
COPY --from=build --chown=node:node /app/dist/standalone ./

USER node

EXPOSE 3000

CMD ["node", "server.js"]
