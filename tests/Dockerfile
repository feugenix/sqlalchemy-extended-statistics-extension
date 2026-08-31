FROM python:3.13-slim as builder

COPY src/ pyproject.toml uv.lock ./

RUN python3.13 -m pip install --upgrade uv
RUN uv sync --lock --no-dev
