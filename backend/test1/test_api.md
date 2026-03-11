uv run uvicorn app.main:app --reload --port 8000

# 1. 基础健康检查
curl http://localhost:8000/api/v1/health

# 2. 详细组件状态
curl http://localhost:8000/api/v1/health/detail

# 3. 打开 Swagger 文档
start http://localhost:8000/docs


buzhidao在测啥
uv run uvicorn app.main:app --reload --port 8000