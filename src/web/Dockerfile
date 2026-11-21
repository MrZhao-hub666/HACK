FROM node:24-alpine AS build
WORKDIR /web
COPY src/web/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --prefer-offline --no-audit --no-fund
COPY src/web/ ./
RUN npm run build

FROM nginx:stable-alpine
COPY src/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist/ /usr/share/nginx/html/
EXPOSE 80
