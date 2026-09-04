from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from backend.app.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(request: Request, x_api_key: str | None = Depends(api_key_header)):
    expected_key = get_settings().api_key
    if not expected_key:
        return x_api_key

    if x_api_key is None or x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    return x_api_key
