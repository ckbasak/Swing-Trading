FROM python:3.11-slim

WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose Hugging Face Spaces default port
EXPOSE 7860

RUN chmod +x start.sh
CMD ["/bin/bash", "./start.sh"]

