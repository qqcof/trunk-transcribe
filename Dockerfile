FROM ubuntu:22.04

# Use the closest mirror instead of default mirror
RUN sed -i 's#http://archive.ubuntu.com/ubuntu/#http://mirror.steadfastnet.com/ubuntu/#g' /etc/apt/sources.list

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
    sox \
    ffmpeg \
    && \
    rm -rf /var/lib/apt/lists/*

ARG DESIRED_CUDA
ARG TARGETPLATFORM
COPY install-whisper.sh /usr/local/bin/install-whisper.sh
RUN install-whisper.sh

ARG WHISPER_MODEL=tiny.en
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN python3 -c "import whisper; import os; whisper.load_model(os.getenv('WHISPER_MODEL'))"

RUN pip3 install poetry>=1.3.2

WORKDIR /src
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && \
    poetry install --without dev --no-root --no-interaction --no-ansi

COPY app app
COPY config config
COPY *.py ./

COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]

ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}

CMD ["worker"]
