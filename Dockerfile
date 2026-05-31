FROM rust:1.87-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8443

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        build-essential \
        cmake \
        pkg-config \
        ca-certificates \
        gcc-mingw-w64-x86-64 \
        gcc-aarch64-linux-gnu \
    && rm -rf /var/lib/apt/lists/*

RUN rustup target add \
        x86_64-pc-windows-gnu \
        x86_64-unknown-linux-gnu \
        aarch64-unknown-linux-gnu

ENV CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=x86_64-w64-mingw32-gcc \
    CARGO_TARGET_X86_64_PC_WINDOWS_GNU_AR=x86_64-w64-mingw32-ar \
    CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc \
    CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_AR=aarch64-linux-gnu-ar

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/server/requirements.txt

COPY agent/Cargo.toml agent/Cargo.lock /app/agent/
COPY agent/src /app/agent/src
RUN cargo fetch --manifest-path /app/agent/Cargo.toml

COPY server /app/server
COPY README.md /app/README.md

WORKDIR /app/server

EXPOSE 8443

CMD ["python", "run.py"]
