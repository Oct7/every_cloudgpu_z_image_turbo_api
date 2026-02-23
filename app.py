from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import io
import torch
import base64
import os
import uuid
import asyncio
import math
import requests
from concurrent.futures import ThreadPoolExecutor
from diffusers import ZImagePipeline

app = FastAPI(title="Z-Image-Turbo API")

# 전역 상태 및 동시 처리 설정 (Worker 수를 1로 하여 순차 처리 = Queue 방식)
pipe = None
executor = ThreadPoolExecutor(max_workers=1)
# 글로벌 요청 카운터 유지용
active_requests = 0

@app.on_event("startup")
def load_model():
    global pipe
    print("Checking CUDA availability...")
    
    # 1. GPU 연결 확인 및 상세 정보 출력
    if not torch.cuda.is_available():
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("ERROR: CUDA is NOT available to PyTorch/torch.cuda.")
        print(f"Device count: {torch.cuda.device_count()}")
        print(f"PyTorch version: {torch.__version__}")
        print("Check if NVIDIA Drivers and Container Toolkit are correctly configured.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        # 즉시 종료하지 않고 로그를 남기기 위해 계속 진행하거나 예외 발생
        raise RuntimeError("No CUDA GPUs are available for the application.")

    print(f"CUDA is available. Device: {torch.cuda.get_device_name(0)}")
    print("Loading Z-Image-Turbo pipeline (this may take a few minutes)...")
    
    try:
        # Official Tongyi-MAI model을 사용하여 모델 로드 
        pipe = ZImagePipeline.from_pretrained(
            "Tongyi-MAI/Z-Image-Turbo",
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=False,
        )
        
        # GPU로 모델 이동
        print("Moving model to CUDA...")
        pipe.to("cuda")
        
        # 선택사항: Flash Attention이 지원되면 활성화 (A100인 경우 강력 권장)
        try:
            # A100은 flash attention을 완벽히 지원합니다.
            pipe.transformer.set_attention_backend("flash")
            print("Bright News: Flash Attention enabled successfully!")
        except Exception as e:
            print("Flash Attention setup failed, falling back to default.", e)
            
        print("Model loaded successfully!")
    except Exception as e:
        print(f"Failed to load model: {str(e)}")
        raise e

class GenerateRequest(BaseModel):
    prompt: str
    ratio: str = "1:1"             # "1:1", "16:9", "9:16" 등 가로세로 비율
    pixel: float = 1.0             # 메가 픽셀 (백만 픽셀) 기준. 예: 1.0 = 대략 1024x1024
    num_inference_steps: int = 4  # Z-Image-Turbo 권장 스텝 수
    guidance_scale: float = 0.0   # Turbo 모델은 0으로 설정 권장
    seed: int = -1                # -1로 하면 랜덤 시드 사용
    upload_url: str = None        # 클라이언트가 전달한 S3 Pre-signed URL (선택)

@app.get("/status")
def get_status():
    """
    현재 API의 상태를 반환합니다.
    status: "ready", "loading", "busy"
    active_requests: 대기/처리 중인 총 요청 수
    """
    if pipe is None:
        return {"status_code": 200, "status": "loading", "active_requests": active_requests}
    
    # 큐에 대기중이거나 처리중인 작업이 없다면 "ready"
    if active_requests == 0:
        return {"status_code": 200, "status": "ready", "active_requests": 0}
    else:
        return {"status_code": 200, "status": "busy", "active_requests": active_requests}

def _generate_task(req: GenerateRequest):
    """실제로 GPU에서 모델을 추론하는 동기 함수 (Worker Thread에서 실행됨)"""
    global pipe
    if req.seed == -1:
        seed = torch.seed() % (2**32)
        generator = torch.Generator("cuda").manual_seed(seed)
    else:
        seed = req.seed
        generator = torch.Generator("cuda").manual_seed(seed)

    # 1. 크기 계산: ratio (예: "16:9")와 pixel (백만 픽셀)을 기반으로 최적의 W, H 도출
    try:
        rw, rh = req.ratio.split(':')
        aspect_ratio = float(rw) / float(rh)
    except Exception:
        aspect_ratio = 1.0  # 파싱 실패나 오류 시 기본 1:1 적용
        
    target_total_pixels = req.pixel * 1_000_000
    
    # h = sqrt(target_pixels / aspect_ratio), w = h * aspect_ratio
    calc_h = math.sqrt(target_total_pixels / aspect_ratio)
    calc_w = calc_h * aspect_ratio
    
    # 디퓨전 모델인 특성상 가로세로 길이는 통상적으로 16 또는 32의 배수여야 함
    # Z-Image의 패치 처리 특성을 고려해 32의 배수로 반올림
    final_h = int(round(calc_h / 32.0)) * 32
    final_w = int(round(calc_w / 32.0)) * 32
    
    # 너무 작아지는 경우를 대비한 최소값 방어
    final_h = max(32, final_h)
    final_w = max(32, final_w)

    # 이미지 생성
    output = pipe(
        prompt=req.prompt,
        height=final_h,
        width=final_w,
        num_inference_steps=req.num_inference_steps,
        guidance_scale=req.guidance_scale,
        generator=generator
    )
    
    image = output.images[0]
    
    # 이미지를 byte 객체로 저장
    img_io = io.BytesIO()
    image.save(img_io, format="PNG")
    img_bytes = img_io.getvalue()
    
    # Pre-signed URL을 활용한 능동적 S3 직접 업로드 (키리스, Keyless)
    if req.upload_url:
        try:
            # 중앙 서버가 발급해준 일회용 권한 URL로 이미지를 바로 쏘아 보냅니다.
            upload_res = requests.put(
                req.upload_url,
                data=img_bytes,
                headers={"Content-Type": "image/png"}
            )
            upload_res.raise_for_status() 
            
            # 여기서 upload_url은 "https://bucket.s3.../파일.png?AWSAccessKeyId=..." 의 형태인데,
            # 물음표 앞의 순수 URL만 잘라서 반환해줍니다.
            pure_url: str = req.upload_url.split("?")[0]
            return {
                "status_code": 200,
                "image_url": pure_url,
                "seed": seed
            }
        except Exception as e:
            # 외부 업로드 실패 시 더 이상 Fallback 하지 않고 전용 에러 반환 (사용자 요청 사항)
            return {
                "status_code": 500,
                "error": str(e),
                "message": "Storage problem: Failed to upload image to S3"
            }

    # 전달받은 upload_url이 없을 때만 기존처럼 base64 반환 동작 수행
    encoded_img = base64.b64encode(img_bytes).decode("utf-8")
    return {
        "status_code": 200,
        "image_base64": f"data:image/png;base64,{encoded_img}",
        "seed": seed
    }

@app.post("/generate")
async def generate_image(req: GenerateRequest):
    global pipe, active_requests
    if pipe is None:
        raise HTTPException(status_code=503, detail="Model is still loading")

    # 요청이 들어오면 카운터 증가
    active_requests += 1

    try:
        # ThreadPoolExecutor를 이용해 _generate_task 함수를 비동기 큐에 집어넣음
        # max_workers=1 이므로 한 번에 하나씩만 GPU 추론을 수행 (자연스러운 Queue 구조)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(executor, _generate_task, req)
        
        return JSONResponse(content=result)
        
    except Exception as e:
        # 오류 발생 시 구체적인 에러 메시지 응답
        return JSONResponse(
            status_code=500,
            content={
                "status_code": 500,
                "error": str(e), 
                "message": "Failed to generate image or upload to server"
            }
        )
    finally:
        # 작업이 끝나거나 에러가 나더라도 카운트를 감소
        active_requests -= 1
