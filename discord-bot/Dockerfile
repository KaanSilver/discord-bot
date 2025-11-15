FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --default-timeout=100 --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium 

# Copy the bot code
COPY . .

# Default command to run bot
CMD ["python", "bot.py"]