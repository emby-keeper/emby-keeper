FROM embykeeper/embykeeper:v8.1.0

# Hugging Face Docker Spaces run the container as UID 1000 and proxy the port
# declared by ``app_port`` in the Space README (1818 for the upstream Space).
# The data directory lives outside /app, which is a declared VOLUME in the base
# image and therefore not a safe place to pre-create files.
ENV HOME=/data \
    EMBYKEEPERAPI_BASEDIR=/data
RUN mkdir -p /data && chown -R 1000:1000 /data

CMD ["web", "--port", "1818"]
