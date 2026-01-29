# src/hart_protocol/message_parser.py
from typing import Dict, Any, Optional, Tuple

START_SHORT = 0x02  # HART short frame delimiter
START_LONG  = 0x82  # HART long frame delimiter

def compute_checksum(core_without_chk: bytes) -> int:
    """
    XOR усіх байтів (старт..дані), checksum такий, що XOR(включно з ним)=0.
    Отже checksum = XOR(core_without_chk) ^ 0x00
    """
    s = 0
    for b in core_without_chk:
        s ^= b
    # під час побудови ми повертаємо 'chk', який зробить загальний XOR=0, тобто chk == s
    return s

def verify_checksum(core_with_chk: bytes) -> bool:
    s = 0
    for b in core_with_chk:
        s ^= b
    return (s & 0xFF) == 0

def build_short_address(poll_addr: int) -> bytes:
    """
    Формує коротку адресу за форматом (1 байт):
    Bit 7: Primary Master (1)
    Bit 6: Burst Mode (0 - not implemented)
    Bit 5-4: Reserved (0)
    Bit 3-0: Slave Address (0-15)
    Приклад: Slave 1 -> 1000 0001 -> 0x81
    """
    # 0x80 встановлює старший біт (Primary Master)
    # 0x0F гарантує, що адреса слейва не вилізе за межі 0-15
    return bytes([0x80 | (int(poll_addr) & 0x0F)])

def build_long_address(unique_id_bytes: bytes) -> bytes:
    """
    Приймає 5 байт Unique ID (Manuf + DevType + Serial).
    Повертає 5 байт Long Address для кадру.
    Вимога протоколу: Bit 7 першого байту має бути 1 (Primary Master).
    """
    if not unique_id_bytes or len(unique_id_bytes) != 5:
        # Fallback (якщо передали щось не те)
        return bytes([0x80, 0x00, 0x00, 0x00, 0x00])
    
    # Копіюємо байти
    addr = bytearray(unique_id_bytes)
    # Встановлюємо старший біт у 1 (Primary Master)
    addr[0] = addr[0] | 0x80
    return bytes(addr)

def parse_request_frame(raw: bytes) -> Optional[Dict[str, Any]]:
    """
    Повертає dict:
    {
      'preambles': int,
      'start': int,
      'address': bytes,
      'command': int,
      'byte_count': int,
      'data': bytes,
      'checksum': int
    }
    або None якщо не можна розібрати.
    """
    if not raw:
        return None
    i = 0
    n = len(raw)
    # підрахунок преамбул 0xFF
    preambles = 0
    while i < n and raw[i] == 0xFF:
        preambles += 1
        i += 1
    if i >= n:
        return None
    start = raw[i]
    i += 1
    if start == 0x02 or start == 0x06:
        addr_len = 1
    # 0x82 (Master Long) або 0x86 (Slave Long Response) -> 5 байт адреси
    elif start == 0x82 or start == 0x86:
        addr_len = 5
    else:
        return None
    # ------------------------------------------------------------------
    if i + addr_len + 2 > n:  # командний(1) + байтконт(1)
        return None
    address = raw[i:i+addr_len]
    i += addr_len
    command = raw[i]
    i += 1
    bc = raw[i]
    i += 1
    if i + bc + 1 > n:
        return None
    data = raw[i:i+bc]
    i += bc
    chk = raw[i]
    core = bytes([start]) + address + bytes([command]) + bytes([bc]) + data
    if not verify_checksum(core + bytes([chk])):
        # все одно повернемо, щоб GUI показав RX, але позначимо invalid
        pass
    return {
        "preambles": preambles,
        "start": start,
        "address": address,
        "command": command,
        "byte_count": bc,
        "data": data,
        "checksum": chk
    }

def parse_response_frame(raw: bytes) -> Optional[Dict[str, Any]]:
    """
    У відповіді після BC йдуть 2 байти статусу (status1,status2) + payload.

    Повертаємо те саме, що й parse_request_frame, але:
      - status1/status2 винесені окремо
      - поле "data" містить ТІЛЬКИ payload (без статусів)
      - поле "raw_data" містить bytes включно зі статусами (status+payload)
    """
    parsed = parse_request_frame(raw)
    if parsed is None:
        return None

    raw_data = parsed.get("data", b"")
    if isinstance(raw_data, (bytes, bytearray)) and len(raw_data) >= 2:
        parsed["status1"] = raw_data[0]
        parsed["status2"] = raw_data[1]
        payload = bytes(raw_data[2:])
    else:
        parsed["status1"] = None
        parsed["status2"] = None
        payload = b""

    parsed["raw_data"] = bytes(raw_data) if isinstance(raw_data, (bytes, bytearray)) else b""
    parsed["data"] = payload
    return parsed
