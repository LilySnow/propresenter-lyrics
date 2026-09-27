# Web interface for propresenter-lyrics.
# Works on Hugging Face Spaces (Docker SDK, port 7860) and Google Cloud Run ($PORT).
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install the package straight from GitHub (change @main to a tag to pin a version)
RUN pip install --no-cache-dir streamlit \
    "propresenter-lyrics @ git+https://github.com/LilySnow/propresenter-lyrics.git@main"

# Hugging Face runs containers as a non-root user
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app
COPY --chown=user app.py .

ENV PORT=7860
EXPOSE 7860
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 \
    --server.headless=true --browser.gatherUsageStats=false \
    --client.toolbarMode=viewer
