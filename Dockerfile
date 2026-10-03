# libc pairing: both stages use the same python:3.14-slim base, so libooz.so is
# compiled against exactly the glibc/libstdc++ it is loaded with at runtime.
# That is the whole point of building in this image rather than a separate
# builder distro. The library is built here, not copied: it is not in the repo
# (ooz/bin/* is gitignored) and zao/ooz publishes only a Windows prebuilt.
FROM python:3.14-slim AS ooz-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# zao/ooz pinned to a commit, not a branch, so the image is reproducible.
ARG OOZ_COMMIT=ff5aeb9e45e362e8d6bb1199aa82406285dd2a18
WORKDIR /src
# The target is named `libooz`, so CMake emits liblibooz.so; it is installed
# under the name decompress.py expects.
# Build invocation is the one decompress.py records in its own error message.
RUN git clone --recurse-submodules https://github.com/zao/ooz.git \
    && git -C ooz checkout "$OOZ_COMMIT" \
    && git -C ooz submodule update --init --recursive \
    && cmake -B build -DOOZ_BUILD_EXE=OFF -DOOZ_BUILD_BUN=OFF -DOOZ_BUILD_VALIDATE=OFF -S ooz \
    && cmake --build build \
    && cp build/liblibooz.so /libooz.so \
    && test -f /libooz.so

FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PALSAVE_API_OOZ_LIB_PATH=/opt/palsave-api/lib/libooz.so

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=ooz-build /libooz.so /opt/palsave-api/lib/libooz.so
COPY *.py ./

# Matches `id palsave-api` on the host (uid 992, gid 979). The host's extra
# group (palworld) is supplied at runtime by compose, not baked in. No home
# directory and no login shell: nothing here needs either.
RUN groupadd --gid 979 palsave-api \
    && useradd --uid 992 --gid 979 --no-create-home --shell /usr/sbin/nologin palsave-api
USER 992:979

ENTRYPOINT ["python", "main.py"]
