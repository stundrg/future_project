FROM python:3.11-slim

WORKDIR /app/generator

# 의존성 설치를 코드 복사보다 먼저 → 빌드 캐시 최대 활용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

CMD ["python", "main.py"]
