# src/hart_protocol/bus.py
import time
import threading
from typing import Dict, Optional, Tuple, Any

from .message_parser import (
    parse_request_frame, compute_checksum, verify_checksum,
    START_SHORT, START_LONG
)

class HARTBus:
    def __init__(self, delay_ms: int = 200, min_address: int = 0, max_address: int = 63, preambles: int = 5):
        self.delay_ms = int(delay_ms)
        self.min_address = int(min_address)
        self.max_address = int(max_address)
        self.preambles = int(preambles)
        self._slaves: Dict[int, Any] = {}
        self._lock = threading.Lock()

    # settings API
    def set_delay(self, ms: int): self.delay_ms = int(ms)
    def set_preambles(self, n: int): self.preambles = max(3, min(int(n), 7))
    def get_settings(self):
        return {
            "min_address": self.min_address,
            "max_address": self.max_address,
            "delay_ms": self.delay_ms,
            "preambles": self.preambles
        }

    def register_slave(self, polling_address: int, slave_device: Any):
        with self._lock:
            self._slaves[int(polling_address) & 0x3F] = slave_device

    def is_address_taken(self, addr: int) -> bool:
        """Перевіряє, чи є вже пристрій з такою адресою на шині."""
        with self._lock:
            return (int(addr) & 0x3F) in self._slaves

    def move_slave(self, old_addr: int, new_addr: int):
        """Переміщує пристрій на нову адресу у внутрішній пам'яті шини."""
        with self._lock:
            old_addr = int(old_addr) & 0x3F
            new_addr = int(new_addr) & 0x3F
            
            if old_addr in self._slaves:
                device = self._slaves.pop(old_addr) # Видаляємо зі старої
                self._slaves[new_addr] = device     # Записуємо на нову
                # Також оновлюємо внутрішню пам'ять самого девайсу (на всяк випадок)
                if hasattr(device, 'polling_address'):
                    device.polling_address = new_addr

    def scan_devices(self):
        with self._lock:
            out = []
            for addr, dev in sorted(self._slaves.items(), key=lambda x: x[0]):
                out.append({
                    "address": addr,
                    "unique_id": dev.unique_id_str,
                    "device_id": f"{dev.serial_number:06X}",
                    "model": dev.model,
                    "manufacturer": dev.manufacturer
                })
        time.sleep(self.delay_ms / 1000.0)
        return out

    def _route_to_slave(self, polling_address: int):
        with self._lock:
            return self._slaves.get(int(polling_address) & 0x3F, None)

    def transact_frame(self, request: bytes) -> bytes:
        """
        Приймає повний RAW кадр, парсить, відправляє у потрібний slave.handle_request(),
        очікує delay, повертає повний RAW кадр відповіді.
        """
        parsed = parse_request_frame(request)
        if parsed is None:
            # повернемо "порожню" помилкову відповідь (для логів)
            return b""

        # --- FIX: Запам'ятовуємо, скільки преамбул прийшло у запиті ---
        # message_parser.py повертає поле "preambles" у словнику parsed
        incoming_preambles_count = parsed.get("preambles", self.preambles)
        # --------------------------------------------------------------

        # polling address беремо з короткої адреси або з логічної таблиці
        addr_field = parsed["address"]
        if parsed["start"] == START_SHORT:
            polling = addr_field[0] & 0x3F
        else:
            # логіка для long frame (залишаємо як було)
            polling = getattr(self, "_forced_polling_for_long", None)
            if polling is None:
                try:
                    polling = addr_field[-1] & 0x3F
                except Exception:
                    return b""

        slave = self._route_to_slave(polling)
        if not slave:
            # немає відповіді
            time.sleep(self.delay_ms / 1000.0)
            return b""

        # прокидаємо виклик у slave
        time.sleep(self.delay_ms / 1000.0)
        resp_core = slave.handle_request(parsed)  # це вже [START][ADDR..][CMD][BC][DATA]
        if not resp_core:
            return b""

        # сформуємо повний кадр: використовуємо incoming_preambles_count замість self.preambles
        chk = compute_checksum(resp_core)
        
        # --- FIX: Формуємо відповідь з тією ж кількістю преамбул ---
        frame = bytes([0xFF]) * incoming_preambles_count + resp_core + bytes([chk])
        
        return frame