SHELL := /bin/bash

DOCKER_COMPOSE = $(shell (docker compose > /dev/null 2>&1 && echo "docker compose") || echo "docker-compose")

build:
	$(DOCKER_COMPOSE) build

start: .env config/notifications.json
	$(DOCKER_COMPOSE) up -d

stop:
	$(DOCKER_COMPOSE) stop

deps:
	bin/install-whisper.sh
	poetry install --with dev

fmt:
	black .

restart:
	$(DOCKER_COMPOSE) restart api worker

test: start
	@diff config/whisper.json config/whisper.json.testing
	python3 -m unittest -k tests.integration

coverage:
	coverage run -m unittest -k tests.unit

retest: restart test

.PHONY: build deps fmt restart test
