# Local-only synthetic workbench. No cloud deployment, API keys or paid calls.
.PHONY: dev backend-tests frontend-tests browser-tests check

dev:
	bash scripts/dev.sh

backend-tests:
	.venv/bin/python -m pytest backend/tests/ -q

frontend-tests:
	npm test --prefix frontend -- --run

browser-tests:
	cd frontend && CI=true npx playwright test --workers=1

check: backend-tests frontend-tests
	npm run build --prefix frontend
	npm run lint --prefix frontend
