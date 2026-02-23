# Z-Image-Turbo FastAPI Server

이 프로젝트는 Kakao Cloud, Nebius.ai 등의 GPU 환경에서 `Tongyi-MAI/Z-Image-Turbo` 모델을 고성능 API로 제공하기 위한 서버입니다. NVIDIA A100 등 최신 GPU에 최적화되어 있으며, **멀티 GPU 병렬 처리** 및 **S3 직접 업로드** 기능을 내장하고 있습니다.

## 🚀 빠른 시작 가이드 (One-Click Deployment)

Ubuntu GPU 인스턴스(추천: Kakao Cloud NVIDIA 이미지)에서 아래 명령어만 입력하면 모든 설정이 완료됩니다.

```bash
# 1. 레포지토리 클론
git clone https://github.com/Oct7/every_cloudgpu_z_image_turbo_api.git
cd every_cloudgpu_z_image_turbo_api

# 2. API Key 및 GPU 설정
# API_KEY: 보안을 위해 필수 변경 권장
# TARGET_GPU_IDS: 사용할 GPU 번호들을 쉼표로 구분 (예: 0,1)
echo "API_KEY=your-custom-secret-key" > .env
echo "TARGET_GPU_IDS=0,1" >> .env

# 3. 원클릭 설치 및 실행
sudo chmod +x setup.sh
./setup.sh
```

**처리 내용:** Docker 설치 ➔ NVIDIA Container Toolkit 설정 ➔ GPU 최적화 빌드 ➔ 멀티 GPU 모델 로드 ➔ 상시 서버 구동(`--restart always`)

---

## 🔒 보안 및 환경 설정

본 서버는 공개된 IP에서 GPU 자원을 보호하기 위해 **API Key 인증**을 요구합니다.

-   **API_KEY**: 프로젝트 루트의 `.env` 파일에 저장합니다. 모든 API 호출 시 헤더에 `X-API-Key: {값}`을 포함해야 합니다.
-   **TARGET_GPU_IDS**: 병렬 처리에 사용할 GPU 인덱스 목록입니다. 지정된 개수만큼 이미지를 동시에 생성할 수 있습니다.

---

## 📩 API 사용 가이드

### 1. 이미지 생성 (`POST /generate`)

이미지를 생성합니다. 설정된 GPU 개수만큼 **병렬(Concurrent) 처리**가 가능합니다.

#### 요청 파라미터 (JSON)
- `prompt` (String, 필수): 생성할 이미지 묘사
- `ratio` (String, 기본 "1:1"): 가로세로 비율 (예: "16:9", "9:16", "3:2")
- `pixel` (Float, 기본 1.0): 목표 메가픽셀 (1.0 = 약 1024x1024)
- `seed` (Int, 기본 -1): 랜덤 시드 (-1: 랜덤)
- `upload_url` (String, 선택): **S3 Pre-signed URL (PUT)**. 전달 시 S3로 자동 업로드합니다.

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

---

### 2. 서버 및 워커 상태 확인 (`GET /status`)

현재 서버의 가동 상태와 가용 GPU 워커 수를 확인합니다.

```bash
curl http://{서버_IP}:8000/status -H "X-API-Key: your-custom-secret-key"
```

#### 응답 예시
```json
{
  "status_code": 200,
  "status": "ready",
  "active_requests": 1,        // 현재 처리 중인 요청 수
  "total_worker_count": 2,     // 설정된 총 GPU(워커) 수
  "idle_worker_count": 1       // 즉시 사용 가능한 GPU 수
}
```

---

### 3. 전체 GPU 하드웨어 모니터링 (`GET /status/gpu`)

관리자를 위해 서버에 장착된 **모든 GPU**의 온도, 메모리, 전력 상태를 반환합니다.

```bash
curl http://{서버_IP}:8000/status/gpu -H "X-API-Key: your-custom-secret-key"
```

#### 응답 예시
```json
{
  "status_code": 200,
  "total_gpu_count": 2,
  "active_worker_count": 2,
  "gpus": [
    {
      "index": 0,
      "name": "NVIDIA A100 80GB PCIe",
      "is_active_serving": true,
      "temperature_c": 35,
      "memory": { "utilization_percent": 30.5 },
      "power_usage_w": 95.2
    },
    ...
  ]
}
```

---

## 💡 주요 특징 및 최적화

-   **멀티 GPU 병렬 처리**: `ThreadPoolExecutor`와 GPU 자원 풀을 결합하여 여러 요청을 동시에 처리합니다.
-   **Flash Attention**: A100 GPU에서 최상의 추론 속도를 내도록 설정되어 있습니다.
-   **무상태(Stateless) 설계**: 서버 내부의 AWS Key 없이 클라이언트가 제공한 `upload_url`만으로 안전하게 S3 업로드를 수행합니다.

---

## 🛠 트러블슈팅

**GPU가 인식되지 않는 경우 (A100 전용):**
MIG 모드가 활성화되어 있다면 동작하지 않을 수 있습니다. 아래 명령을 실행한 후 재부팅하세요.
```bash
sudo nvidia-smi -mig 0
sudo reboot
```

**문의 및 지원**: [Github Issues](https://github.com/Oct7/every_cloudgpu_z_image_turbo_api/issues)
