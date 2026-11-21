FROM nginx:stable-alpine
COPY src/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY src/web/index.html src/web/app.js src/web/app-template.js src/web/shared.js src/web/styles.css /usr/share/nginx/html/
COPY src/web/components/ /usr/share/nginx/html/components/
COPY src/web/vendor/ /usr/share/nginx/html/vendor/
EXPOSE 80
