FROM ghcr.io/puppeteer/puppeteer:23.3.0

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=false \
    NODE_ENV=production

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY server.js ./

EXPOSE 8200
CMD ["node", "server.js"]
