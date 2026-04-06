# ── Stage 1: build qsharp wheel from source ─────────────────────────────────
FROM public.ecr.aws/lambda/python:3.13 AS builder

# Install build tools + Rust
RUN dnf install -y gcc gcc-c++ make openssl-devel git && \
    curl -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.88.0 --profile minimal

ENV PATH="/root/.cargo/bin:$PATH"

# Install maturin
RUN pip install --upgrade pip maturin

# Clone qsharp at v1.27.0 (shallow)
RUN git clone --depth 1 --branch v1.27.0 https://github.com/microsoft/qsharp.git /qsharp

# Build the Python wheel
WORKDIR /qsharp/source/pip
RUN maturin build --release --out /wheels

# Install all non-qsharp deps
RUN pip install \
    "fastapi>=0.135.1" \
    "uvicorn[standard]>=0.42.0" \
    "pydantic>=2.12.5" \
    "pydantic-settings>=2.13.1" \
    "pyqasm>=1.0.1" \
    "mangum>=0.21.0" \
    -t /install/

# Install the built qsharp wheel (with its Python deps)
RUN pip install /wheels/qsharp-*.whl -t /install/

# ── Stage 2: final Lambda image ──────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.13

COPY --from=builder /install/ /var/task/
COPY app/ /var/task/app/
COPY handler.py /var/task/

CMD ["handler.lambda_handler"]
