build:
	docker compose build

start:
	docker compose up -d

deps:
	pip install -r requirements.txt -r requirements-dev.txt

fmt:
	black app tests

restart: start
	docker compose restart web worker

test:
	python -m unittest

.PHONY: build deps fmt restart test
