FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN pip install uv && uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

COPY . .

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "truss_kernel.main:app", "--host", "0.0.0.0", "--port", "8000"]
