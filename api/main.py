import collections.abc
import contextlib

import fastapi

import api.core.config
import api.core.logging
import api.src.events.routes
import api.src.events.service
import api.src.system.routes

#
# Set up logging configuration
#

api.core.logging.setup_logging()

#
# Set up logger for this module
#

logger = api.core.logging.get_logger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI) -> collections.abc.AsyncIterator[None]:
    """Share one HTTP client (and its connection pool) across requests."""

    with api.src.events.service.create_http_client() as client:
        app.state.http_client = client
        yield


app = fastapi.FastAPI(
    title=api.core.config.settings.PROJECT_NAME,
    description="Proton Calendar has no public API. This gives you one: any day's events as JSON.",
    version="0.5.0",
    debug=api.core.config.settings.DEBUG,
    lifespan=lifespan,
    license_info={
        "name": "GPL-3.0-only",
        "url": "https://www.gnu.org/licenses/gpl-3.0.html",
    },
)

#
# Include routers
#

app.include_router(api.src.events.routes.router)
app.include_router(api.src.system.routes.router)
