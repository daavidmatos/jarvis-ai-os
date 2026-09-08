.PHONY: run test docker clean
run:
	uvicorn jarvis.api:app --reload --port 8000

test:
	pytest

docker:
	docker compose up --build

clean:
	rm -f jarvis.db
