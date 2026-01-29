# src/hart_protocol/commands.py

# --- Universal commands (0–19 already had) ---
CMD_READ_UNIQUE_ID = 0
CMD_READ_PV = 1
CMD_READ_LOOP_CURRENT_PCT = 2
CMD_READ_DV_AND_CURRENT = 3
CMD_WRITE_POLLING_ADDR = 6
CMD_READ_UID_BY_TAG = 11
CMD_READ_MESSAGE = 12
CMD_READ_TAG_DESC_DATE = 13
CMD_READ_PV_XDCR_INFO = 14
CMD_READ_OUTPUT_INFO = 15
CMD_READ_SERIAL_NUMBER = 16
CMD_WRITE_MESSAGE = 17
CMD_WRITE_TAG_DESC_DATE = 18
CMD_WRITE_SERIAL_NUMBER = 19

# --- NEW: Long Tag & additional universal commands (rev.5) ---
CMD_READ_LONG_TAG = 20                 # Read Long Tag
CMD_READ_UID_BY_LONG_TAG = 21          # Read Unique Identifier Associated With Long Tag
CMD_WRITE_LONG_TAG = 22                # Write Long Tag
CMD_RESET_CFG_CHANGED = 38             # Reset Configuration Changed Flag
CMD_READ_ADDITIONAL_STATUS = 48        # Read Additional Device Status

# --- Constants for field lengths ---
LONG_TAG_LEN = 32

# --- Utility helpers for fixed-size ASCII fields ---
def pack_ascii_fixed(s: str, size: int) -> bytes:
    """
    Pack ASCII string to fixed size with zero padding.
    """
    b = (s or "").encode("ascii", errors="ignore")[:size]
    return b + b"\x00" * (size - len(b))

def unpack_ascii_fixed(b: bytes) -> str:
    """
    Unpack fixed-size ASCII field, stripping trailing zeroes.
    """
    try:
        return b.decode("ascii", errors="ignore").rstrip("\x00")
    except Exception:
        return ""
