# Bau-Umgebung: Ubuntu 24.04 (wie Zorin OS 18), per Digest gepinnt.
# Netz braucht nur dieser Schritt; gebaut wird danach mit --network=none.
FROM docker.io/library/ubuntu@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      g++ cmake ninja-build pkg-config make \
      libpam0g-dev libsystemd-dev \
      libpam-wrapper libpamtest0-dev pamtester \
      python3 strace file binutils ca-certificates v4l-utils gettext \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
