# Pinned to a specific patch release, by digest, for reproducible builds.
# Bump deliberately; check https://hub.docker.com/_/python/tags for updates,
# then re-resolve the digest (e.g. `docker buildx imagetools inspect
# python:3.11.15-slim` or via the registry API) — do not just edit the tag.
FROM python:3.11.15-slim@sha256:b27df5841f3355e9473f9a516d38a6783b6c8dfeacaf2d14a240f443b368ddb6

WORKDIR /app

# Exact versions match what's tested against (see requirements_dev.txt /
# manifest.json) so a rebuild of this commit always installs the same code.
RUN pip install --no-cache-dir \
    pyserial==3.5 \
    paho-mqtt==2.1.0

# Copy parser, structs, and the sidecar entry point
COPY docker/pylontech_parser.py .
COPY docker/structs.py .
COPY docker/main.py .

ENV PYTHONUNBUFFERED=1

# Run as an unprivileged user rather than root. Membership in "dialout"
# (present by default in Debian-based images) grants access to serial
# devices like /dev/ttyUSB0 under the default udev permissions (group
# dialout, mode 660) used by most USB-serial adapters. If your host's
# "dialout" GID differs from the container's, add
# `group_add: ["<host-gid>"]` (see `getent group dialout` on the host) to
# docker-compose.yml. TCP mode does not need this at all.
#
# /data is created and chowned here so a *fresh* named volume mounted over it
# inherits this ownership (Docker copies a mount point's existing content and
# ownership into a new, empty named volume). Volumes created by an older,
# root-based image will already be root-owned — see the README's
# Troubleshooting section for the one-time chown needed when upgrading.
RUN useradd --system --create-home --home-dir /app --shell /usr/sbin/nologin pylon2mqtt \
    && usermod -aG dialout pylon2mqtt \
    && mkdir -p /data \
    && chown -R pylon2mqtt:pylon2mqtt /app /data
USER pylon2mqtt

CMD ["python", "main.py"]
