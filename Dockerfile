FROM docker.io/library/python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FLASK_APP=app:app FLASK_DEBUG=false
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unixodbc-dev \
    libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/microsoft.deb \
    && dpkg -i /tmp/microsoft.deb && rm /tmp/microsoft.deb \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements/azure.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && useradd --create-home --uid 10001 app
COPY registry registry
COPY migrations migrations
COPY app.py .
COPY docker-entrypoint.sh .
RUN mkdir -p registry/static/stamps registry/static/signatures instance \
    && chown -R app:app registry/static/stamps registry/static/signatures instance
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "app:app"]
