# Z-Image-Turbo FastAPI Server

이 프로젝트는 Nebius.ai, Kakao Cloud 등의 환경에서 GPU 호스팅을 할 수 있도록 `Tongyi-MAI/Z-Image-Turbo` 모델을 FastAPI로 서빙할 수 있게 구성된 API 서버입니다.

## 🚀 빠른 시작 가이드 (가장 권장)

GitHub 등에서 코드를 다운로드 받으신 뒤, 카카오 클라우드 등 **Ubuntu GPU 인스턴스**에서 아래 명령어 단 **한 줄**만 입력하시면, **Docker 설치 ➔ NVIDIA 드라이버 세팅 ➔ 모델 가중치 다운 ➔ 상시 서버 구동**까지 모두 원클릭으로 완료됩니다!

```bash
sudo chmod +x setup.sh && ./setup.sh
```

*(참고: 빌드 시 가장 최신의 모델 가중치를 서버 내부에 다운로드 받으므로 처음 한 번은 네트워크 상황에 따라 시간이 소요될 수 있습니다.)*

---

### (선택) 수동으로 직접 띄우고 싶을 경우

#### 1. Docker 이미지 빌드

```bash
docker build -t z-image-turbo-api .
```

### 2. Docker 컨테이너 실행

GPU를 사용하여 8000번 포트로 서버를 엽니다. (NVIDIA Container Toolkit 설치 필요)
이 서버 자체는 AWS 접근 권한(Key)을 일절 요구하지 않는 무상태(Stateless) 컨테이너로 작동합니다.

```bash
docker run -d --restart=always --gpus all -p 8000:8000 z-image-turbo-api
```

## 📩 API 요청 방법

서버가 실행된 후, `POST /generate` 엔드포인트에 요청을 보내면 이미지를 생성하여 반환합니다.

### 📍 테스트용 curl 요청 예시 (API Key 필요)

서버의 모든 API는 헤더에 `X-API-Key`를 포함해야 작동합니다.

```bash
curl -X POST "http://카카오서버공인IP:8000/generate" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your-secret-key-1234" \
     -d '{
         "prompt": "Beautiful cinematic lighting photography...",
         "ratio": "16:9",
         "pixel": 1.5,
         "seed": 42
     }'
```

- `upload_url` 파라미터(옵션)에 중앙 서버(우리 회사 서버)가 S3로부터 발급받은 **Pre-signed URL**을 담아서 보내면, 이미지 생성 직후 서버가 S3로 다이렉트 PUT 업로드(Keyless)를 수행합니다.
- `upload_url`을 전달하지 않으면 기존처럼 Base64 이미지 문자열로 다이렉트 응답을 반환합니다.

응답 예시 (S3 **upload_url** 전달 및 업로드 성공 시):
```json
{
  "status_code": 200,
  "image_url": "https://company-s3-bucket.s3.ap-northeast-2.amazonaws.com/temp_2026.png",
  "seed": 42
}
```

응답 예시 (**upload_url** 전달 시 업로드 실패 시 - Storage Error):
```json
{
  "status_code": 500,
  "error": "Reason of failure...",
  "message": "Storage problem: Failed to upload image to S3"
}
```

응답 예시 (업로드 파라미터 미전달 시 - Base64 반환):
```json
{
  "status_code": 200,
  "image_base64": "data:image/png;base64,iVBORw0KGgo...",
  "seed": 42
}
```

에러 응답 예시 (예외 발생 시):
```json
{
  "status_code": 500,
  "error": "Error details here",
  "message": "Failed to generate image or upload to server"
}
```

웹 UI나 프론트엔드 서비스에서 `"image_base64"` 내용을 그대로 `<img>` 태그의 `src` 로 매핑하시거나 `"image_url"`을 이용해 직접 렌더링하시면 됩니다.

---

## 💡 모델의 로딩 방식에 대한 안내

질문해주신 4가지 다운로드 URL(Comfy-Org에서 배포한 safetensors) 파일들은 **ComfyUI(노드 베이스 툴) 전용** 폴더 구조(예: `diffusion_models`, `text_encoders`, `vae`)를 위해 분할된 커스텀 가중치들입니다.

이를 파이썬 코드로 독립적인 API 엔진으로 구현할 때에는, HuggingFace의 표준 프레임워크인 `diffusers` 라이브러리를 사용하여 공식 베포 버전을 직접 불러오는 것이 정석적이고 안정적입니다. 그 이유는 다음과 같습니다:
1. **의존성 감소:** ComfyUI 아키텍처를 통째로 올리기에는 무겁고 오버헤드가 크며, 불필요한 기능이 많습니다. `diffusers`를 사용하면 순수 파이썬 + FastAPI만으로 모델을 서빙할 수 있습니다.
2. **최신 지원:** `diffusers`는 최근 업데이트(PR #12703, #12715)를 통해 Z-Image-Turbo에 대한 네이티브 지원을 병합했습니다. 

*(본 프로젝트는 내부적으로 `Tongyi-MAI/Z-Image-Turbo`의 전체 가중치를 받아오게 되며, 이는 질문자님께서 첨부해주신 세분화된 파일들과 완벽하게 동일한 아키텍처(Diffusion: z_image_turbo_bf16, VAE: ae, Text Encoder: Qwen-3B 등)를 포함하고 있습니다.)*

만약, 무조건적으로 다운로드하신 `safetensors` 파일들 그 자체를 그대로 맵핑하여 사용하셔야만 한다면, 이 코드를 ComfyUI API 스크립트 기반으로 전면 수정하여야 합니다. 그러나 현재 제공해드린 `diffusers` 기반의 파이썬 코드가 클라우드 배포와 운영 효율 면에서 가장 효율적이라고 권장해 드립니다!

### 📡 API 헬스체크 및 큐 상태 점검
`GET /status` 엔드포인트를 호출하면 현재 서버가 이미지 생성 작업을 한가하게 대기 중인지, 혹은 바쁘게 처리 중인지 확인할 수 있습니다.
여러 대로 서버를 늘릴 경우, 이 API를 통해 가장 비어있는(active_requests가 적은) 서버로 로드밸런싱을 구축할 수 있습니다.

```bash
curl "http://localhost:8000/status"
```

응답 예시:
```json
{
  "status_code": 200,
  "status": "ready",
  "active_requests": 0
}
```
