# =====================================================================
# DOCKERFILE - Minimal, Universal UPS Web Dashboard
# Multi-architecture compatible: linux/amd64, linux/arm64, linux/arm/v7
# Zero external pip dependencies, memory footprint < 15 MB
# =====================================================================

FROM python:3.12-alpine

LABEL maintainer="UPS Dashboard"
LABEL description="Minimal zero-dependency web dashboard for Network UPS Tools (NUT)"

WORKDIR /app

# Create unprivileged system user with standard UID 1000
RUN addgroup -g 1000 -S appgroup && adduser -u 1000 -S appuser -G appgroup

# Copy application files
COPY dashboard /app/dashboard
COPY app.py /app/app.py
COPY VERSION /app/VERSION
COPY static /app/static

# Set permissions and create data directory
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + str(__import__('os').getenv('PORT', 8080)) + '/api/health')" || exit 1

CMD ["python", "app.py"]
