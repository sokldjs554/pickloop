FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 MESA_SHADER_CACHE_DIR=/tmp/mesa
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git g++ ffmpeg libegl1 libegl-mesa0 libgl1-mesa-dri libopengl0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=build_ca,target=/etc/ssl/certs/ca-certificates.crt python -m pip install --cert /etc/ssl/certs/ca-certificates.crt --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch==2.7.1+cpu' 'torchvision==0.22.1+cpu'
RUN --mount=type=secret,id=build_ca,target=/etc/ssl/certs/ca-certificates.crt python -m pip install --cert /etc/ssl/certs/ca-certificates.crt --no-cache-dir 'mujoco==3.3.7' 'numpy==2.2.6' 'scipy==1.15.3' \
    'opencv-python-headless==4.11.0.86' 'Pillow==11.2.1' 'py-trees==2.3.0'
