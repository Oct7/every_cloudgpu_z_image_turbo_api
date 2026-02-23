#!/bin/bash

# 1. Update and install basic dependencies
echo "Updating system and installing base dependencies..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# 2. Install Docker (if not installed)
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing Docker..."
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
    echo "Docker is already installed."
fi

# 3. Install NVIDIA Container Toolkit (if not installed)
if ! command -v nvidia-ctk &> /dev/null; then
    echo "NVIDIA Container Toolkit not found. Installing..."
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
      && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list \
      && sudo apt-get update \
      && sudo apt-get install -y nvidia-container-toolkit
    
    # Configure NVIDIA Container Toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
else
    echo "NVIDIA Container Toolkit is already installed."
fi

# 4. Check for NVIDIA Driver on Host
if ! command -v nvidia-smi &> /dev/null; then
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "ERROR: NVIDIA Driver not found on host machine."
    echo "Please run: sudo apt-get update && sudo apt-get install -y nvidia-driver-535-server"
    echo "Then REBOOT your machine before running this script again."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    exit 1
fi

# 5. Build Docker image
echo "Building Z-Image-Turbo-API Docker image..."
sudo docker build -t z-image-turbo-api .

# 6. Run Docker container
echo "Starting Z-Image-Turbo-API container..."

# Check for API_KEY and TARGET_GPU_ID in environment or .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -z "$API_KEY" ]; then
    echo "WARNING: API_KEY is not set. Using default key."
    API_KEY="your-secret-key-1234"
fi

if [ -z "$TARGET_GPU_ID" ]; then
    echo "Using default GPU 0 (Change by setting TARGET_GPU_ID in .env)"
    TARGET_GPU_ID=0
fi

# Stop and remove existing container if it exists
sudo docker stop z-image-turbo-api-container 2>/dev/null || true
sudo docker rm z-image-turbo-api-container 2>/dev/null || true

# Run container with GPUs, auto-restart and API Key
sudo docker run -d \
  --name z-image-turbo-api-container \
  --restart=always \
  --gpus all \
  -e API_KEY="$API_KEY" \
  -e TARGET_GPU_ID="$TARGET_GPU_ID" \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -p 8000:8000 \
  z-image-turbo-api

echo "=========================================="
echo "Deployment Complete!"
echo "Server is running on port 8000."
echo "Check logs with: sudo docker logs -f z-image-turbo-api-container"
echo "=========================================="
