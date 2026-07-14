import logging
import hmac
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import get_settings

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()


def verify_access_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
):
    settings = get_settings()
    is_valid = hmac.compare_digest(
        credentials.credentials.encode(),
        settings.API_ACCESS_TOKEN.encode(),
    )
    if not is_valid:
        logger.warning("Unauthorized access attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
