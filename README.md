# Z-Image-Turbo FastAPI Server

이 프로젝트는 Kakao Cloud, Nebius.ai 등의 GPU 환경에서 `Tongyi-MAI/Z-Image-Turbo` 모델을 고성능 API로 제공하기 위한 서버입니다. NVIDIA A100 등 최신 GPU에 최적화되어 있으며, S3 직접 업로드 기능을 내장하고 있습니다.

## 🚀 빠른 시작 가이드 (One-Click Deployment)

Ubuntu GPU 인스턴스(추천: Kakao Cloud NVIDIA 이미지)에서 아래 명령어만 입력하면 모든 설정이 완료됩니다.

```bash
# 1. 레포지토리 클론
git clone https://github.com/Oct7/every_cloudgpu_z_image_turbo_api.git
cd every_cloudgpu_z_image_turbo_api

# 2. API Key 설정 (보안을 위해 필수 변경 권장)
echo "API_KEY=your-custom-secret-key" > .env

# 3. 원클릭 설치 및 실행
sudo chmod +x setup.sh
./setup.sh
```

**처리 내용:** Docker 설치 ➔ NVIDIA Container Toolkit 설정 ➔ GPU 최적화 빌드 ➔ 모델 자동 다운로드 ➔ 상시 서버 구동(`--restart always`)

---

## 🔒 보안 및 환경 설정

본 서버는 공개된 IP에서 GPU 자원을 보호하기 위해 **API Key 인증**을 요구합니다.

-   **설정**: 프로젝트 루트의 `.env` 파일에 `API_KEY=값` 형태로 저장합니다.
-   **사용**: 모든 API 호출 시 HTTP 헤더에 `X-API-Key: {값}`을 포함해야 합니다.

---

## 📩 API 사용 가이드

### 1. 이미지 생성 (`POST /generate`)

이미지를 생성하고 결과(Base64 또는 S3 URL)를 반환합니다.

#### 요청 파라미터 (JSON)
- `prompt` (String, 필수): 생성할 이미지 묘사
- `ratio` (String, 기본 "1:1"): 가로세로 비율 (예: "16:9", "9:16", "3:2")
- `pixel` (Float, 기본 1.0): 목표 메가픽셀 (1.0 = 약 1024x1024)
- `seed` (Int, 기본 -1): 랜덤 시드 (-1: 랜덤)
- `upload_url` (String, 선택): **S3 Pre-signed URL (PUT)**. 전달 시 이미지를 해당 경로로 자동 업로드합니다.

#### 요청 예시 (curl)
```bash
curl -X POST "http://{서버_IP}:8000/generate" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your-custom-secret-key" \
     -d '{
         "prompt": "Cyberpunk city at night, rain, neon lights, 4k photography",
         "ratio": "16:9",
         "pixel": 1.0,
         "upload_url": "https://bucket.s3.amazonaws.com/image.png?X-Amz-Signature=..."
     }'
```

#### 응답 예시
- **S3 업로드 시**: `{"status_code": 200, "image_url": "...", "seed": 42}`
- **기본(Base64) 반환 시**: `{"status_code": 200, "image_base64": "data:image/png;base64,...", "seed": 42}`

---

### 2. 서버 상태 확인 (`GET /status`)

현재 GPU의 작업 가능 여부 및 대기열 상태를 확인합니다.

```bash
curl http://{서버_IP}:8000/status -H "X-API-Key: your-custom-secret-key"
```

---

## 💡 주요 특징 및 최적화

-   **NVIDIA A100 최능 최적화**: `Flash Attention`을 활성화하여 연산 속도를 극대화했습니다.
-   **무중단 서비스**: 서버 재부팅 시 Docker 컨테이너가 자동으로 다시 실행됩니다.
-   **MIG 모드 자동 대응**: A100의 MIG 설정으로 인한 GPU 인식 불가 문제를 방지하기 위해 드라이버 수준의 가시성을 확보했습니다.
-   **Pre-signed URL 지원**: 서버 내부의 AWS Key 없이도 클라이언트가 제공한 권한을 통해 안전하게 S3에 이미지를 업로드합니다.

---

## 🛠 트러블슈팅

**GPU가 인식되지 않는 경우 (Device count: 0):**
A100 GPU에서 MIG 모드가 활성화되어 있다면 동작하지 않을 수 있습니다. 호스트 터미널에서 아래 명령을 실행한 후 재부팅하세요.
```bash
sudo nvidia-smi -mig 0
sudo reboot
```

**문의 및 지원**: [Github Issues](https://github.com/Oct7/every_cloudgpu_z_image_turbo_api/issues)
