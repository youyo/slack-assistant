# AgentCore Runtime Dockerfile for Slack Bot
# Uses ARM64 architecture for AgentCore Runtime

FROM --platform=linux/arm64 python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV AWS_REGION=ap-northeast-1

# Expose port for AgentCore Runtime
EXPOSE 8080

# Run the AgentCore app
CMD ["python", "handler.py"]
