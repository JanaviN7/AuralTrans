"""FastAPI app. Run with: uvicorn auraltrans.api.app:app --reload --port 8765"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auraltrans.api.routes import router
from auraltrans.recordings import UploadError


def create_app() -> FastAPI:
    app = FastAPI(title="AuralTrans", version="0.1.0")
    # The web dev server proxies /api, so CORS is only a convenience for opening the API directly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(UploadError)
    async def upload_error(_: Request, exc: UploadError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(LookupError)
    async def not_found(_: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    app.include_router(router)
    return app


app = create_app()
