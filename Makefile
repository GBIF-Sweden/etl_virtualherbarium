IMAGE ?= etl_virtualherbarium:latest
CONFIG ?= config-mappings/ume.yml
ACTION ?= process

.PHONY: help build up run download process all strict shell test clean-generated

help:
	@echo "Targets:"
	@echo "  make build                 Build Docker image"
	@echo "  make up                    Run via docker compose with defaults"
	@echo "  make run ACTION=process CONFIG=config-mappings/ups.yml"
	@echo "  make download CONFIG=config-mappings/ups.yml"
	@echo "  make process CONFIG=config-mappings/ups.yml"
	@echo "  make all CONFIG=config-mappings/ups.yml"
	@echo "  make strict CONFIG=config-mappings/ume.yml ACTION=process"
	@echo "  make shell                 Open shell in container"
	@echo "  make test                  Run local tests (requires deps installed)"
	@echo "  make clean-generated       Remove generated malformed/duplicate/report/log files"

build:
	docker build -t $(IMAGE) .

up:
	CONFIG_PATH=$(CONFIG) ACTION=$(ACTION) docker compose up --build --abort-on-container-exit

run:
	docker run --rm \
		-v $(PWD)/config-mappings:/app/config-mappings \
		-v $(PWD)/data:/app/data \
		-v $(PWD)/logs:/app/logs \
		$(IMAGE) python main.py --config $(CONFIG) --action $(ACTION)

download:
	$(MAKE) run ACTION=download CONFIG=$(CONFIG)

process:
	$(MAKE) run ACTION=process CONFIG=$(CONFIG)

all:
	$(MAKE) run ACTION=all CONFIG=$(CONFIG)

strict:
	docker run --rm \
		-v $(PWD)/config-mappings:/app/config-mappings \
		-v $(PWD)/data:/app/data \
		-v $(PWD)/logs:/app/logs \
		$(IMAGE) python main.py --config $(CONFIG) --action $(ACTION) --strict

shell:
	docker run --rm -it \
		-v $(PWD):/app \
		--entrypoint /bin/sh \
		$(IMAGE)

test:
	python -m pytest -q

clean-generated:
	find data/malformed -type f -name '*_malformed.csv' -delete 2>/dev/null || true
	find data/processed -type f \( -name 'duplicates_*.csv' -o -name 'quality_report_*.json' \) -delete
	rm -f logs/app.log
