FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home actuarial
COPY app.py ./
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY data ./data
COPY docs ./docs
RUN mkdir -p runtime reports && chown -R actuarial:actuarial /app
USER actuarial
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--browser.gatherUsageStats", "false"]
