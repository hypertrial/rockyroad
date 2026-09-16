from __future__ import annotations

import uvicorn

from rockyroad_api.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "rockyroad_api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=1,
        factory=False,
    )


if __name__ == "__main__":
    main()
