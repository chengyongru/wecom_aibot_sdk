"""HTTP API client for file download"""

import asyncio
from typing import Tuple

import aiohttp

from .crypto import decrypt_file, extract_filename
from .types.config import WSClientOptions
from .logger import Logger, DefaultLogger


class WeComApiClient:
    """HTTP API client for file operations"""

    def __init__(self, options: WSClientOptions, logger: Logger | None = None):
        self._options = options
        self._logger = logger or DefaultLogger()
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._options.request_timeout / 1000)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def download_file(self, url: str, aes_key: str) -> Tuple[bytes, str | None]:
        """
        Download and decrypt file

        Args:
            url: File URL
            aes_key: AES key for decryption (Base64 encoded)

        Returns:
            Tuple of (decrypted buffer, filename)
        """
        session = await self._get_session()

        async with session.get(url) as response:
            response.raise_for_status()
            encrypted_data = await response.read()

            # Extract filename from Content-Disposition header
            content_disposition = response.headers.get("Content-Disposition", "")
            filename = extract_filename(content_disposition) if content_disposition else None

        # Decrypt file
        decrypted_data = decrypt_file(encrypted_data, aes_key)

        self._logger.debug(f"Downloaded and decrypted file: {filename}, size: {len(decrypted_data)} bytes")

        return decrypted_data, filename
