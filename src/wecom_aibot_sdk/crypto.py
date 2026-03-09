"""AES-256-CBC file decryption module"""

import base64

from Crypto.Cipher import AES


def decrypt_file(encrypted_data: bytes, aes_key: str) -> bytes:
    """
    Decrypt file using AES-256-CBC

    Args:
        encrypted_data: Encrypted file data
        aes_key: AES key (Base64 encoded)

    Returns:
        Decrypted file data
    """
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
