"""File-type validation for real document uploads. Deliberately dependency-
free (no python-magic/libmagic) — a client-supplied Content-Type header is
never trusted alone; for the binary types we check the actual leading bytes
of the file, which a client can't fake without the file genuinely being
that format.
"""
from app.exceptions import UnsupportedFileTypeError

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}

_MAGIC_BYTES: dict[str, bytes] = {
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".pdf": b"%PDF",
}


def extension_of(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def validate_upload(filename: str, content: bytes) -> str:
    """Returns the server-determined mime type, or raises
    UnsupportedFileTypeError. Never trusts the client's declared
    Content-Type — validates extension + (for binary types) actual file
    signature instead.
    """
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UnsupportedFileTypeError(f"Unsupported file extension {ext!r}. Allowed: {allowed}")

    if ext == ".webp":
        # WebP's signature is split ("RIFF" + 4-byte size + "WEBP"), not a
        # simple prefix — a plain startswith() check doesn't fit here.
        if not (content[:4] == b"RIFF" and content[8:12] == b"WEBP"):
            raise UnsupportedFileTypeError("File content does not match a valid .webp file (signature check failed)")
    elif ext in _MAGIC_BYTES:
        signature = _MAGIC_BYTES[ext]
        if not content.startswith(signature):
            raise UnsupportedFileTypeError(
                f"File content does not match a valid {ext} file (signature check failed)"
            )
    else:
        # .txt: no magic-byte signature exists for plain text. Reject
        # anything that isn't valid UTF-8 text or contains null bytes, as a
        # basic guard against a disguised binary with a .txt extension.
        if b"\x00" in content:
            raise UnsupportedFileTypeError("File claims to be .txt but contains binary (null) bytes")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedFileTypeError("File claims to be .txt but is not valid UTF-8 text") from exc

    return ALLOWED_EXTENSIONS[ext]
