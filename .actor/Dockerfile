# Use Apify's Python image for best compatibility
FROM apify/actor-python:3.11

# Copy requirements first for better caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set Python path
ENV PYTHONPATH=/usr/src/app

# Run the actor
CMD ["python", "-m", "src"]
