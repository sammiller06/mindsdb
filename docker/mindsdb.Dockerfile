# Bare mindsdb with no extras is built as a separate stage for caching
FROM python:3.10 as build
COPY . /mindsdb
WORKDIR /mindsdb
RUN --mount=type=cache,target=/root/.cache/pip pip install "."


# Install extras on top of the bare mindsdb
FROM build as extras
ARG EXTRAS
RUN --mount=type=cache,target=/root/.cache/pip if [ -n "$EXTRAS" ]; then pip install $EXTRAS; fi


# Copy installed pip packages and install only what we need
FROM python:3.10-slim
# "rm ... docker-clean" stops docker from removing packages from our cache
# https://vsupalov.com/buildkit-cache-mount-dockerfile/
RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt update && apt-get upgrade -y \
    && apt-get install -y libmagic1 libpq5

COPY --link --from=extras /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

ENV FLASK_DEBUG "1"

EXPOSE 47334/tcp
EXPOSE 47335/tcp
EXPOSE 47336/tcp
