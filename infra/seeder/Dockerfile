# One-shot demo seeder (Phase 08 demo profile).
# Carries a 956 KB gzipped seed-42 bundle — NOT raw CSVs (pitfall P4).
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /seed
COPY infra/demo/bundle-seed42.tar.gz /seed/bundle.tar.gz
COPY infra/seeder/seed.py /seed/seed.py
CMD ["python", "/seed/seed.py"]
