# 公勝保險 差旅／費用報帳 APP
# 需要 LibreOffice（Writer + Calc）才能正確轉檔保留 .xls 格式，僅裝 core 套件會導致轉檔全部失敗。
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-calc fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY templates/ templates/

ENV HOME=/tmp
WORKDIR /app/backend

EXPOSE 8000
# Render/Railway 等平台會用 $PORT 環境變數指定實際對外的埠號，本機沒設定時預設 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
