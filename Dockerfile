FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-noto-core \
    fonts-noto-color-emoji \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r brambet && useradd -r -g brambet brambet

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p temp output assets/fonts \
    && chown -R brambet:brambet /app \
    && chmod 700 /app/temp /app/output

RUN python -c "
import urllib.request
urllib.request.urlretrieve(
    'https://github.com/google/fonts/raw/main/ofl/notosansarabic/NotoSansArabic%5Bwdth%2Cwght%5D.ttf',
    'assets/fonts/NotoSansArabic-Bold.ttf'
)
urllib.request.urlretrieve(
    'https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf',
    'assets/fonts/NotoSans-Bold.ttf'
)
"

USER brambet

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log", "--proxy-headers"]
