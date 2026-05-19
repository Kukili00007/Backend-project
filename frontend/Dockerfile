FROM nginx:1.27-alpine

WORKDIR /usr/share/nginx/html

COPY index.html styles.css app.js config.template.js ./
COPY nginx.conf.template /etc/nginx/conf.d/default.conf.template

EXPOSE 8080

CMD ["/bin/sh", "-c", "export PORT=${PORT:-8080}; export API_BASE_URL=${API_BASE_URL:-}; envsubst '${API_BASE_URL}' < /usr/share/nginx/html/config.template.js > /usr/share/nginx/html/config.js; envsubst '${PORT}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf; nginx -g 'daemon off;'"]
