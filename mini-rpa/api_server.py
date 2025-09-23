import asyncio
import aiohttp
from aiohttp import web
import pandas as pd
import logging
from typing import Dict
from regtech_rpa import RegTechRPA

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('regtech_rpa.log'),
        logging.StreamHandler()
    ]
)

async def handle_request(request: web.Request) -> web.Response:
    """Process API request with controls."""
    logger = logging.getLogger(__name__)
    logger.info("Received API request")
    try:
        data = await request.json()  # Sanitize input
        if not isinstance(data, dict):
            logger.error("Invalid JSON input")
            raise ValueError("Invalid JSON")
        
        config = {'source_type': 'api', 'config': {'endpoints': data.get('endpoints', [])}}
        rpa = RegTechRPA(config)
        result = await rpa.run()
        logger.info("API request processed successfully")
        return web.json_response(result.to_dict(orient='records'))
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return web.Response(text=str(e), status=400)

async def init_app(queue_max: int = 10) -> web.Application:
    """Initialize API server with rate limiting."""
    app = web.Application()
    queue = asyncio.Queue(maxsize=queue_max)
    
    async def limited_handler(request: web.Request) -> web.Response:
        logger = logging.getLogger(__name__)
        logger.debug("Checking queue for rate limiting")
        await queue.put(1)
        try:
            return await handle_request(request)
        finally:
            queue.get_nowait()
            logger.debug("Request processed, queue updated")
    
    app.router.add_post('/process', limited_handler)
    return app