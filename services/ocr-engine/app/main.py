import logging
from . import config
from .routes import create_app

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format=config.LOG_FORMAT
)

# Create FastAPI application
app = create_app()
