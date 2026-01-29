# src/hart_protocol/master.py
from typing import Optional, Tuple
from .message_parser import (
    build_short_address, build_long_address,
    compute_checksum, verify_checksum,
    START_SHORT, START_LONG
)

class HARTMaster:
    """
    Будівник/відправник кадрів HART від майстра.
    frame_format: "short" або "long"
    """
    def __init__(self, bus, frame_format: str = "short", bitwise_decode: bool = False):
        self.bus = bus
        self.frame_format = frame_format
        self.bitwise_decode = bitwise_decode
        self._preambles = 5  # типове
        # фіксований розширений довгий адрес для демо (мануф/девтайп/серіал задає slave)
        # майстер не мусить знати його наперед, це поле використовується тільки якщо обрано LONG у GUI

    def set_frame_format(self, fmt: str):
        self.frame_format = "long" if str(fmt).lower().startswith("l") else "short"

    def set_preambles(self, n: int):
        self._preambles = max(3, min(int(n), 7))

    def build_request(self, polling_addr: int, command: int, data: bytes = b"") -> bytes:
        """
        Будує повний кадр запиту:
        [FF x N][START][ADDR...][CMD][BC][DATA...][CHK]
        """
        preambles = bytes([0xFF]) * self._preambles

        if self.frame_format == "long":
            start = START_LONG
            addr = build_long_address(polling_addr)  # Ми включаємо polling у LSB, інші поля підхопить шина/слейв
        else:
            start = START_SHORT
            addr = build_short_address(polling_addr)

        cmd = bytes([command & 0xFF])
        bc = bytes([len(data) & 0xFF])

        core = bytes([start]) + addr + cmd + bc + data
        chk = compute_checksum(core)
        return preambles + core + bytes([chk])

    def transact(self, polling_addr: int, command: int, data: bytes = b"") -> bytes:
        req = self.build_request(polling_addr, command, data)
        return self.bus.transact_frame(req)
