FROM nginx:1.27-alpine

WORKDIR /usr/share/nginx/html

COPY index.html styles.css app.js config.template.js ./

EXPOSE 80

CMD ["/bin/sh", "-c", ": ${API_BASE_URL:=http://localhost:8000}; envsubst < /usr/share/nginx/html/config.template.js > /usr/share/nginx/html/config.js && nginx -g 'daemon off;'"]
