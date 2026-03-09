"""AES-256-CBC file decryption module"""

import base64
import re
from urllib.parse import unquote

from Crypto.Cipher import AES


def decrypt_file(encrypted_data: bytes, aes_key: str) -> bytes:
    """
    Decrypt file using AES-256-CBC

    Args:
        encrypted_data: Encrypted file data
        aes_key: AES key (Base64 encoded)

    Returns:
        Decrypted file data

    Raises:
        ValueError: If parameters are invalid or decryption fails
    """
    # Parameter validation (consistent with official Node.js SDK)
    if not encrypted_data or len(encrypted_data) == 0:
        raise ValueError("decrypt_file: encrypted_data is empty or not provided")

    if not aes_key or not isinstance(aes_key, str):
        raise ValueError("decrypt_file: aes_key must be a non-empty string")

    try:
        # Base64 decode the key (add padding if needed)
        padding_needed = 4 - (len(aes_key) % 4)
        if padding_needed != 4:
            aes_key = aes_key + "=" * padding_needed
        key = base64.b64decode(aes_key)

        # IV is the first 16 bytes of AESKey (per WeCom documentation)
        iv = key[:16]

        # AES-256-CBC decryption
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted_data)

        # Manual PKCS#7 unpadding (supports 32-byte block as per WeCom docs)
        # WeCom uses PKCS#7 padding to 32-byte boundary, not standard 16-byte
        pad_len = decrypted[-1]
        if pad_len < 1 or pad_len > 32 or pad_len > len(decrypted):
            raise ValueError(f"Invalid PKCS#7 padding value: {pad_len}")

        # Verify all padding bytes are consistent
        for i in range(len(decrypted) - pad_len, len(decrypted)):
            if decrypted[i] != pad_len:
                raise ValueError("Invalid PKCS#7 padding: padding bytes mismatch")

        return decrypted[:-pad_len]

    except Exception as e:
        raise ValueError(
            f"decrypt_file: Decryption failed - {str(e)}. "
            "This may indicate corrupted data or an incorrect aes_key."
        ) from e


def extract_filename(content_disposition: str) -> str:
    """
    Extract filename from Content-Disposition header

    Supports RFC 5987 format (filename*=UTF-8''xxx) and standard format.
    Performs URL decoding for encoded filenames.

    Args:
        content_disposition: Content-Disposition header value

    Returns:
        Filename (URL decoded if necessary), or "unknown_file" if not found
    """
    if not content_disposition:
        return "unknown_file"

    # Priority 1: Match RFC 5987 format: filename*=UTF-8''xxx
    # This format is used for non-ASCII filenames like Chinese
    utf8_match = re.search(r"filename\*=UTF-8''([^;\s]+)", content_disposition, re.IGNORECASE)
    if utf8_match:
        return unquote(utf8_match.group(1))

    # Priority 2: Match standard format: filename="xxx" or filename=xxx
    match = re.search(r'filename="?([^";\s]+)"?', content_disposition, re.IGNORECASE)
    if match:
        return unquote(match.group(1))

    return "unknown_file"
