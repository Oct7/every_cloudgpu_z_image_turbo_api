FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

# 1. 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    wget \
    make \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# 2. 파이썬 의존성 복사 및 설치
COPY requirements.txt .

# pip 최신화 및 캐시 없이 패키지 설치
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. 플래시 어텐션(선택 사항) 설치 시 주석 해제하여 사용할 수 있습니다.
# RUN pip install flash-attn --no-build-isolation

# 4. 애플리케이션 소스 복사
COPY download_model.py .
COPY app.py .

# 5. 모델 가중치 미리 다운로드하여 이미지에 포함 (시작 속도 최적화)
# 주의: 이 과정은 빌드 중 인터넷 연결을 요구하며, 저장 공간을 크게 차지합니다.
RUN python download_model.py

# 6. 포트 노출
EXPOSE 8000

# 7. 서버 실행
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
