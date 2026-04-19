VENV        := qre-env
UVICORN     := $(VENV)/bin/uvicorn
LAMBDA_PORT := 9000
LOCAL_IMAGE := qre-backend:local

.PHONY: activate dev build test clean

activate:
	@echo "Run: source $(VENV)/bin/activate"

## Local dev server (hot reload)
dev:
	$(UVICORN) app.main:app --reload

## Build the Docker image locally (same image used in production)
build:
	@echo "▶ Building image..."
	@docker build --platform linux/amd64 -t $(LOCAL_IMAGE) .
	@echo "✓ Built $(LOCAL_IMAGE)"

## Spin up local Lambda container, smoke test all 3 endpoints, tear down
test: build
	@echo "▶ Starting Lambda runtime..."
	@docker run -d --name qre-test -p $(LAMBDA_PORT):8080 $(LOCAL_IMAGE) > /dev/null
	@sleep 3
	@echo "▶ Testing /health..."
	@curl -sf -X POST http://localhost:$(LAMBDA_PORT)/2015-03-31/functions/function/invocations \
		-H "Content-Type: application/json" \
		-d '{"version":"2.0","routeKey":"GET /health","rawPath":"/health","rawQueryString":"","headers":{"host":"localhost"},"requestContext":{"http":{"method":"GET","path":"/health","sourceIp":"127.0.0.1"}},"isBase64Encoded":false}' | python3 -m json.tool
	@echo "▶ Testing /qasm/validate..."
	@curl -sf -X POST http://localhost:$(LAMBDA_PORT)/2015-03-31/functions/function/invocations \
		-H "Content-Type: application/json" \
		-d '{"version":"2.0","routeKey":"POST /api/v1/qasm/validate","rawPath":"/api/v1/qasm/validate","rawQueryString":"","headers":{"host":"localhost","content-type":"application/json"},"requestContext":{"http":{"method":"POST","path":"/api/v1/qasm/validate","sourceIp":"127.0.0.1"}},"body":"{\"code\":\"OPENQASM 2.0;\\ninclude \\\"qelib1.inc\\\";\\nqreg q[2];\\ncreg c[2];\\nh q[0];\\ncx q[0],q[1];\\nmeasure q -> c;\"}","isBase64Encoded":false}' | python3 -m json.tool
	@echo "▶ Testing /qasm/analyze (this takes ~15s)..."
	@curl -sf -X POST http://localhost:$(LAMBDA_PORT)/2015-03-31/functions/function/invocations \
		-H "Content-Type: application/json" \
		-d '{"version":"2.0","routeKey":"POST /api/v1/qasm/analyze","rawPath":"/api/v1/qasm/analyze","rawQueryString":"","headers":{"host":"localhost","content-type":"application/json"},"requestContext":{"http":{"method":"POST","path":"/api/v1/qasm/analyze","sourceIp":"127.0.0.1"}},"body":"{\"code\":\"OPENQASM 2.0;\\ninclude \\\"qelib1.inc\\\";\\nqreg q[2];\\ncreg c[2];\\nh q[0];\\ncx q[0],q[1];\\nmeasure q -> c;\"}","isBase64Encoded":false}' | python3 -m json.tool
	@docker stop qre-test > /dev/null
	@echo "✓ All tests passed"

clean:
	@docker rmi $(LOCAL_IMAGE) 2>/dev/null || true
