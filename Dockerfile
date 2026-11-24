FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MUJOCO_GL=egl LIBGL_ALWAYS_SOFTWARE=1 MESA_SHADER_CACHE_DIR=/tmp/mesa
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgl1-mesa-dri libopengl0 g++ ffmpeg tesseract-ocr tesseract-ocr-eng fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-lock.txt pyproject.toml ./
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-lock.txt
COPY src src
COPY models models
COPY assets assets
COPY configs configs
COPY web web
COPY cpp cpp
COPY tests tests
COPY scripts scripts
RUN pip install --no-deps -e .
EXPOSE 8000
CMD ["pickloop","serve","--host","0.0.0.0","--port","8000"]
