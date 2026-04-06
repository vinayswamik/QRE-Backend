# ── Stage 1: build qsharp wheel from source ─────────────────────────────────
FROM public.ecr.aws/lambda/python:3.13 AS builder

# Install build tools + Rust
RUN dnf install -y gcc gcc-c++ make openssl-devel git && \
    curl -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal

ENV PATH="/root/.cargo/bin:$PATH"

# Install maturin
RUN pip install --upgrade pip maturin

# Clone qsharp at v1.27.0 (shallow)
RUN git clone --depth 1 --branch v1.27.0 https://github.com/microsoft/qsharp.git /qsharp

# Build the Python wheel
WORKDIR /qsharp/source/pip
RUN maturin build --release --out /wheels

# Install all non-qsharp deps
COPY requirements-no-qsharp.txt /tmp/
RUN pip install -r /tmp/requirements-no-qsharp.txt -t /install/

# Install the built qsharp wheel (with its Python deps)
RUN pip install /wheels/qsharp-*.whl -t /install/

# ── Stage 2: final Lambda image ──────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.13

COPY --from=builder /install/ /var/task/
COPY app/ /var/task/app/
COPY handler.py /var/task/

CMD ["handler.lambda_handler"]
