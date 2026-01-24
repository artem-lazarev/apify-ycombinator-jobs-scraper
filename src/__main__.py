"""Entry point for the Apify actor."""
import asyncio
import logging
from .main import main

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == '__main__':
    asyncio.run(main())
