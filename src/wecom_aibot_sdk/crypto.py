"""AES-256-CBC file decryption module"""

import base64
from typing import Tuple

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


def decrypt_file(encrypted_data: bytes, aes_key: str) -> bytes:
    """
    Decrypt file using AES-256-CBC

    Args:
        encrypted_data: Encrypted file data
        aes_key: AES key (Base64 encoded)

    Returns:
        Decrypted file data
    """
    # Base64 decode the key
    key = base64.b64decode(aes_key)

    # First 16 bytes are IV
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]

    # AES-256-CBC decryption
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)

    return decrypted


def extract_filename(content_disposition: str) -> str:
    """
    Extract filename from Content-Disposition header

    Args:
        content_disposition: Content-Disposition header value

    Returns:
        Filename
    """
    if "filename=" in content_disposition:
        parts = content_disposition.split("filename=")
        if len(parts) > 1:
            filename = parts[1].strip('"\'')
            return filename
    return "unknown_file"
