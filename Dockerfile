FROM python:3.11-slim

# Install Chrome, ChromeDriver and dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set environment variables for Selenium to find Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Use Gunicorn for production
# Timeout set to 120s because scraping can be slow
CMD ["gunicorn", "app_enhanced:app", "--bind", "0.0.0.0:8000", "--timeout", "120"]
