FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --system eims && useradd --system --gid eims --home-dir /app eims
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
COPY . .
RUN mkdir -p /app/instance/evidence && chown -R eims:eims /app
USER eims
EXPOSE 8000
CMD ["sh", "scripts/container-entrypoint.sh"]
