"""Celery worker entry point."""

import os
import sys
import logging

# Configure logging before importing app modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.celery_app import celery_app

if __name__ == "__main__":
    celery_app.start()