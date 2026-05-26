FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# libmagic1 is required by python-magic for MIME sniffing of uploaded files.
# Without it the validate_uploaded_file() check fails closed and refuses every
# upload — which is safe-but-broken. Install it explicitly here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend /app
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

FROM base AS dev

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS prod

CMD ["/app/entrypoint.sh"]
