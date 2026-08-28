SHELL := /bin/bash
PY := python3
REPOS := tobymao/sqlglot python-poetry/tomlkit pallets/click arrow-py/arrow
MODEL ?= google/gemini-2.5-flash
SPLIT ?= eval

.PHONY: help repos images dataset validate demo baseline solution eval report replay test clean-results

help:
	@echo "Repro-Bot — turn a bug report into a verified failing test"
	@echo ""
	@echo "  make repos       clone the target repositories (~5 min, ~400 MB)"
	@echo "  make dataset     mine candidate cases from merged bugfix commits"
	@echo "  make validate    build sandbox images and keep only provable cases"
	@echo "  make replay      reproduce every reported number from the shipped cache (no API key)"
	@echo "  make baseline    run both baselines live          (needs OPENROUTER_API_KEY)"
	@echo "  make solution    run the full solver live         (needs OPENROUTER_API_KEY)"
	@echo "  make eval        run every variant live           (needs OPENROUTER_API_KEY)"
	@echo "  make report      rebuild results/REPORT.md from results/"
	@echo "  make demo        run one case end to end, printing the trajectory"
	@echo "  make test        run the harness unit tests (needs uv)"
	@echo ""
	@echo "  MODEL=$(MODEL)  SPLIT=$(SPLIT)"

repos:
	@mkdir -p data/repos
	@for r in $(REPOS); do \
		n=$$(basename $$r); \
		if [ ! -d "data/repos/$$n" ]; then \
			echo "cloning $$r"; git clone -q "https://github.com/$$r.git" "data/repos/$$n"; \
		else echo "have $$n"; fi; \
	done

dataset: repos
	$(PY) -m reprobot.dataset.mine \
		$(foreach r,$(REPOS),--repo $(r)) \
		--limit 4000 --want 26 --out data/cases/mined_all.json

validate:
	$(PY) -m reprobot.dataset.validate \
		--cases data/cases/mined_all.json \
		--out data/cases/validated.json \
		--build-missing --timeout 300

# Replay mode answers the only question that matters for a reader who does not
# want to spend anything: are the numbers in the report real? Every model call
# is served from the committed cache, so this reproduces them exactly, offline.
replay:
	REPROBOT_OFFLINE=1 $(PY) -m reprobot.eval.run \
		--variant b0 --variant b1 --variant s1 --variant s2 --variant s3 --variant s4 \
		--split $(SPLIT) --model $(MODEL) --out-dir results
	$(MAKE) report

baseline:
	$(PY) -m reprobot.eval.run --variant b0 --variant b1 \
		--split $(SPLIT) --model $(MODEL) --out-dir results

solution:
	$(PY) -m reprobot.eval.run --variant s4 \
		--split $(SPLIT) --model $(MODEL) --out-dir results

eval:
	$(PY) -m reprobot.eval.run \
		--variant b0 --variant b1 --variant s1 --variant s2 --variant s3 --variant s4 \
		--split $(SPLIT) --model $(MODEL) --out-dir results
	$(MAKE) report

report:
	$(PY) -m reprobot.eval.report --split $(SPLIT) --out results/REPORT.md

demo:
	$(PY) -m reprobot.demo --model $(MODEL)

# The host stays dependency-free, so the harness tests borrow pytest through uv
# rather than making every reader install something to read the code.
test:
	uv run --quiet --with pytest --python 3.12 python -m pytest tests/ -q

clean-results:
	rm -rf results traces data/memory
