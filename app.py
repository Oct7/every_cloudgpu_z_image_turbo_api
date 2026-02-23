from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
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
import pynvml
import queue

# 보안 설정: 환경 변수에서 API_KEY를 가져오며, 기본값은 임시로 지정 (배포 시 변경 권장)
API_KEY = os.getenv("API_KEY", "your-secret-key-1234")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(header_value: str = Depends(api_key_header)):
    if header_value == API_KEY:
        return header_value
    raise HTTPException(
        status_code=403, detail="Could not validate credentials - Invalid API Key"
    )

app = FastAPI(title="Z-Image-Turbo API")

# 전역 상태 및 동시 처리 설정
pipes = {}  # {gpu_id: pipeline}
# TARGET_GPU_IDS 예: "0,1" -> [0, 1]
gpu_id_str = os.getenv("TARGET_GPU_IDS", os.getenv("TARGET_GPU_ID", "0"))
TARGET_GPU_IDS = [int(x.strip()) for x in gpu_id_str.split(",")]

# 동시 처리를 위한 워커 수 설정 (GPU 개수만큼 병렬 처리)
num_workers = len(TARGET_GPU_IDS)
executor = ThreadPoolExecutor(max_workers=num_workers)
active_requests = 0

# 사용 가능한 GPU 인덱스를 담는 큐
available_gpus = queue.Queue()
for gid in TARGET_GPU_IDS:
    available_gpus.put(gid)

@app.on_event("startup")
def startup_event():
    # pynvml 초기화
    try:
        pynvml.nvmlInit()
        print(f"NVML initialized. Monitoring {pynvml.nvmlDeviceGetCount()} GPUs.")
    except Exception as e:
        print(f"Failed to initialize NVML: {e}")
    load_models_to_gpus()

def load_models_to_gpus():
    global pipes
    print(f"Starting to load models on GPUs: {TARGET_GPU_IDS}")
    
    # 각 GPU에 모델 로드
    for gid in TARGET_GPU_IDS:
        print(f"[{gid}] Checking CUDA availability...")
        if not torch.cuda.is_available():
            print(f"ERROR: CUDA not available for GPU {gid}")
            continue

        print(f"[{gid}] Loading Z-Image-Turbo pipeline...")
        try:
            pipe = ZImagePipeline.from_pretrained(
                "Tongyi-MAI/Z-Image-Turbo",
                torch_dtype=torch.bfloat16,
                low_cpu_mem_usage=False,
            )
            print(f"[{gid}] Moving model to cuda:{gid}...")
            pipe.to(f"cuda:{gid}")
            
            # Flash Attention 활성화
            try:
                pipe.transformer.set_attention_backend("flash")
                print(f"[{gid}] Flash Attention enabled!")
            except Exception as e:
                print(f"[{gid}] Flash Attention fail: {e}")
            
            pipes[gid] = pipe
            print(f"[{gid}] Model loaded successfully on GPU {gid}!")
        except Exception as e:
            print(f"[{gid}] Failed to load on GPU {gid}: {e}")

    if not pipes:
        raise RuntimeError("No GPUs were initialized successfully.")
    print(f"Total {len(pipes)} GPU workers are ready!")

class GenerateRequest(BaseModel):
    prompt: str
    ratio: str = "1:1"             # "1:1", "16:9", "9:16" 등 가로세로 비율
    pixel: float = 1.0             # 메가 픽셀 (백만 픽셀) 기준. 예: 1.0 = 대략 1024x1024
    num_inference_steps: int = 4  # Z-Image-Turbo 권장 스텝 수
    guidance_scale: float = 0.0   # Turbo 모델은 0으로 설정 권장
    seed: int = -1                # -1로 하면 랜덤 시드 사용
    upload_url: str = None        # 클라이언트가 전달한 S3 Pre-signed URL (선택)

@app.get("/status")
def get_status(api_key: str = Depends(get_api_key)):
    if not pipes:
        return {"status_code": 200, "status": "loading", "active_requests": active_requests}
    
    # 사용 가능한 워커 수 대비 현재 요청 수로 상태 판단
    if active_requests < len(pipes):
        return {"status_code": 200, "status": "ready", "active_requests": active_requests, "total_workers": len(pipes)}
    else:
        return {"status_code": 200, "status": "busy", "active_requests": active_requests, "total_workers": len(pipes)}

@app.get("/status/gpu")
def get_gpu_status(api_key: str = Depends(get_api_key)):
    """
    서버에 장착된 모든 GPU의 상세 하드웨어 상태를 리스트로 반환합니다.
    """
    try:
        device_count = pynvml.nvmlDeviceGetCount()
        gpu_list = []
        active_serving_count = 0

        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            power_usage = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
            
            # 현재 이 API 프로세스가 사용 중인 GPU인지 확인
            is_active_serving = (i in TARGET_GPU_IDS)
            if is_active_serving:
                active_serving_count += 1

            gpu_list.append({
                "index": i,
                "name": name,
                "is_active_serving": is_active_serving,
                "memory": {
                    "total_mib": round(mem_info.total / (1024**2), 2),
                    "used_mib": round(mem_info.used / (1024**2), 2),
                    "utilization_percent": round(mem_info.used / mem_info.total * 100, 1)
                },
                "utilization": {
                    "gpu_percent": utilization.gpu,
                    "memory_percent": utilization.memory
                },
                "temperature_c": temp,
                "power_usage_w": round(power_usage, 2)
            })

        return {
            "status_code": 200,
            "total_gpu_count": device_count,
            "active_worker_count": active_serving_count,
            "gpus": gpu_list
        }
    except Exception as e:
        return {
            "status_code": 500,
            "error": str(e),
            "message": "Failed to fetch multi-GPU stats"
        }

def _generate_task(req: GenerateRequest):
    """실제로 GPU에서 모델을 추론하는 동기 함수 (Worker Thread에서 실행됨)"""
    global pipes, available_gpus
    
    # 사용 가능한 GPU 하나 꺼내기 (비어있을 경우 스레드가 여기서 대기함)
    gpu_id = available_gpus.get()
    device = f"cuda:{gpu_id}"
    pipe = pipes[gpu_id]
    
    try:
        if req.seed == -1:
            seed = torch.seed() % (2**32)
            generator = torch.Generator(device).manual_seed(seed)
        else:
            seed = req.seed
            generator = torch.Generator(device).manual_seed(seed)

        # 1. 크기 계산
        rw, rh = req.ratio.split(':')
        aspect_ratio = float(rw) / float(rh)
        target_total_pixels = req.pixel * 1_000_000
        calc_h = math.sqrt(target_total_pixels / aspect_ratio)
        calc_w = calc_h * aspect_ratio
        final_h = int(round(calc_h / 32.0)) * 32
        final_w = int(round(calc_w / 32.0)) * 32
        final_h, final_w = max(32, final_h), max(32, final_w)

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
        img_io = io.BytesIO()
        image.save(img_io, format="PNG")
        img_bytes = img_io.getvalue()
        
        if req.upload_url:
            upload_res = requests.put(req.upload_url, data=img_bytes, headers={"Content-Type": "image/png"})
            upload_res.raise_for_status() 
            pure_url: str = req.upload_url.split("?")[0]
            return {"status_code": 200, "image_url": pure_url, "seed": seed}

        encoded_img = base64.b64encode(img_bytes).decode("utf-8")
        return {"status_code": 200, "image_base64": f"data:image/png;base64,{encoded_img}", "seed": seed}

    except Exception as e:
        return {"status_code": 500, "error": str(e), "message": "Internal processing error"}
    finally:
        # 어떤 상황에서도 GPU 반납
        available_gpus.put(gpu_id)

@app.post("/generate")
async def generate_image(req: GenerateRequest, api_key: str = Depends(get_api_key)):
    global pipes, active_requests
    if not pipes:
        raise HTTPException(status_code=503, detail="Models are still loading")

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
