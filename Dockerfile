# Replace this with your actual application build.
# This placeholder serves a static HTML page via nginx.
FROM nginx:alpine

COPY . /usr/share/nginx/html
