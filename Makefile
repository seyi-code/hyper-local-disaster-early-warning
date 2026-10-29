.PHONY: up down logs sim dashboard-next test-cusum zip

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f anomaly-engine telemetry-broker

sim:
	cd sensors && python simulator.py

dashboard-next:
	cd services/dashboard-next && npm install && NEXT_PUBLIC_API_BASE=http://localhost:3000 npm run dev

test-cusum:
	cd services/anomaly-engine && python tests/test_cusum.py

zip:
	cd .. && zip -r disaster-early-warning.zip disaster-early-warning \
	  -x "*/node_modules/*" "*/.venv/*" "*/__pycache__/*" "*/dist/*" "*/.next/*" "*.pyc"
