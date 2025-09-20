FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Create non-root user with specific UID/GID for volume compatibility
RUN groupadd -r chronos --gid=1000 && useradd -r -g chronos --uid=1000 chronos

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/chronos/.local

# Copy application code
COPY --chown=chronos:chronos . .

# Create required directories with proper permissions
RUN mkdir -p logs data config templates static plugins/custom && \
    chown -R chronos:chronos /app && \
    chmod -R 755 /app/logs /app/data /app/config /app/plugins

# Switch to non-root user
USER chronos

# Make sure scripts in .local are usable
ENV PATH=/home/chronos/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/sync/health || exit 1

# Expose port
EXPOSE 8080

# Default command
CMD ["python", "-m", "src.main"]
