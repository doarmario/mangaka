FROM node:22-bookworm-slim
WORKDIR /api
COPY --from=upstream package.json ./
RUN npm install --no-audit --no-fund
COPY --from=upstream tsconfig.json ./
COPY --from=upstream src ./src
COPY --from=upstream config ./config
COPY server.ts ./src/server.ts
RUN npm run build && npm prune --omit=dev
ENV NODE_ENV=production PORT=3001
USER node
EXPOSE 3001
CMD ["node", "dist/src/server.js"]
