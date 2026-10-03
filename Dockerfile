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
    PALSAVE_API_HOST=0.0.0.0 \
    PALSAVE_API_PORT=8788 \
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

# State lives outside /app, as the systemd unit does (code in one directory,
# WorkingDirectory in another): config.py's state.json and snapshots/ are
# cwd-relative, and state must not live in the directory a deploy replaces.
# /state must exist in the image and be owned by 992:979: Docker initializes a
# fresh named volume from the image's content and ownership at the mount point
# only if that path exists, otherwise the volume is created root-owned and the
# service answers requests while its watcher silently fails every write.
RUN mkdir -p /state && chown 992:979 /state
USER 992:979
WORKDIR /state

# Docker's own health verdict, which is the ONLY thing that separates `running`
# from `unhealthy` on lyly-admin's services board: with no HEALTHCHECK here,
# `docker compose ps` reports an empty Health and the row is green whatever the
# process is doing.
#
# It probes the container's own routable address, not 127.0.0.1, and that is
# the point: a loopback-only bind inside the container answers a loopback probe
# perfectly while the published port reaches nothing. That exact defect shipped
# once on this branch, which is why PALSAVE_API_HOST is 0.0.0.0 above.
# PALSAVE_API_PORT is read at runtime rather than baked in, so the probe
# follows whatever compose sets; unset, it is the 8788 declared above. A
# hardcoded port would leave a service declared on another one permanently
# unhealthy.
#
# What it does NOT prove: that the service is doing any work. /events/new-pals
# answers 200 with an empty list when the watcher has parsed nothing at all --
# so this would not have caught an Oodle library path pointing at nothing,
# because that failure IS a healthy response to every request. Liveness only.
HEALTHCHECK --interval=30s --start-period=30s --start-interval=3s --timeout=5s --retries=3 \
  CMD python -c "import os,socket,urllib.request; urllib.request.urlopen('http://' + socket.gethostbyname(socket.gethostname()) + ':' + os.environ.get('PALSAVE_API_PORT', '8788') + '/events/new-pals?limit=1', timeout=4).read()"

ENTRYPOINT ["python", "/app/main.py"]
