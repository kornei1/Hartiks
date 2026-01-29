# src/devices/base_slave.py
import logging
from random import random
from typing import Tuple, Dict, Any
from struct import pack

from mai.message_parser import START_SHORT, START_LONG, build_short_address

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# HART statuses (very small subset for simulator)
HART_STATUS = {
    "OK": (0x00, 0x00),
    "INVALID_DATA": (0x08, 0x00),        # invalid length/format
    "UNSUPPORTED_CMD": (0x20, 0x00),     # command not supported
    "DEVICE_ERROR": (0x40, 0x00),        # generic device error
}


class BaseSlave:
    """Base HART slave simulator with a set of universal/common commands."""

    hart_major_rev = 5
    device_rev = 1
    software_rev = 1
    min_preambles_required = 3

    def __init__(
        self,
        polling_address: int,
        tag: str,
        model: str,
        manufacturer: str,
        serial_number: int,
    ):
        # Обмежуємо адресу 4 бітами (0-15), бо старші біти зайняті Майстром та Burst-режимом
        self.polling_address = int(polling_address) & 0x0F
        self.tag = (tag or "")[:8]
        self.descriptor = "DESC"
        self.date = (24, 8, 2025)  # D, M, Y
        self.message = "READY"
        self.long_tag = ""  # cmd 22

        self.model = model
        self.manufacturer = manufacturer
        self.serial_number = int(serial_number) & 0xFFFFFF

        # Unique id: manuf_id(1)+dev_type(1)+serial(3)
        self.manuf_id = 0xFE
        self.dev_type = 0x26
        self.unique_id_str = f"{self.manuf_id:02X}{self.dev_type:02X}{self.serial_number:06X}"

        # Loop current mode
        self.loop_current_enabled = 1

        # Variable classes (0=none)
        self.var_classes = [0, 0, 0, 0]

        # PV parameters
        self.upper_range = 100.0
        self.lower_range = 0.0
        self.damping = 1.0
        self.min_span = 1.0

        # Output info (cmd 15)
        self.alarm_code = 0
        self.transfer_code = 0
        self.write_protect = 0

        # Simulated "configuration changed" counter (cmd 38)
        self.config_change_counter = 0

    def update_unique_id(self):
        """Re-calculate unique ID string after changing manuf_id/dev_type."""
        # Unique id: manuf_id(1)+dev_type(1)+serial(3)
        self.unique_id_str = f"{self.manuf_id:02X}{self.dev_type:02X}{self.serial_number:06X}"

    # ---- process variables (override in derived) ----
    def read_pv(self) -> Tuple[float, int]:
        """Returns (value, HART units code)."""
        return 0.0, 57

    def read_sv_tv_qv(self):
    # SV = Electronics Temperature (наприклад, 28°C) - код 32
    # TV і QV поки залишимо 0 (Unused - код 250)
        import random
        elec_temp = 28.0 + random.uniform(-1.0, 1.0) 

    # Повертаємо пари (значення, код_одиниць)
        return (elec_temp, 32), (0.0, 250), (0.0, 250)

    def read_loop_current_and_percent(self) -> Tuple[float, float]:
        # 1. Читаємо значення (воно завжди змінюється, бо там рандом/симуляція)
        pv, _units = self.read_pv()
        
        # 2. Рахуємо відсоток (завжди рахуємо чесно)
        span = self.upper_range - self.lower_range
        if span == 0:
            perc = 0.0
        else:
            perc = ((pv - self.lower_range) / span) * 100.0
            
        # 3. А ось струм залежить від адреси (Спрощена логіка)
        if self.polling_address == 0:
            # Адреса 0 -> Аналоговий режим -> Струм "живий"
            ma = 4.0 + (perc / 100.0) * 16.0
            ma = max(3.8, min(20.8, ma))
        else:
            # Адреса 1-15 -> Multidrop -> Струм фіксований (парковка)
            ma = 4.0
        
        return ma, perc

    # ---- helpers ----
    def _touch_config_changed(self):
        self.config_change_counter = (int(self.config_change_counter) + 1) & 0xFFFF

    def _addr_bytes_short(self) -> bytes:
        return build_short_address(self.polling_address)

    def _response_core(
        self,
        start: int,
        cmd: int,
        data: bytes,
        status: Tuple[int, int] = HART_STATUS["OK"],
    ) -> bytes:
        status1, status2 = status
        # Response BC includes 2 status bytes + payload
        bc = len(data) + 2
        
        # --- FIX: Визначаємо правильний Start Byte для відповіді ---
        # Якщо запит був 0x02 -> відповідь 0x06
        # Якщо запит був 0x82 -> відповідь 0x86
        resp_start = start
        if start == 0x02:
            resp_start = 0x06
        elif start == 0x82:
            resp_start = 0x86
        # -----------------------------------------------------------

        if start == START_SHORT: # 0x02
            addr = self._addr_bytes_short()
        else:
            addr = bytes([
                    self.manuf_id | 0x80, 
                    self.dev_type,
                    (self.serial_number >> 16) & 0xFF,
                    (self.serial_number >> 8) & 0xFF,
                    self.serial_number & 0xFF,
                ])
        
        # Формуємо пакет, використовуючи новий resp_start
        return bytes([resp_start]) + addr + bytes([cmd, bc, status1, status2]) + data

    def error_response(self, start: int, cmd: int, status: Tuple[int, int]) -> bytes:
        logger.warning(f"Error response: cmd={cmd}, status={status}")
        return self._response_core(start, cmd, b"", status)

    # ---- command processor ----
    def handle_request(self, req: Dict[str, Any]) -> bytes:
        start = req["start"]
        cmd = req["command"]
        data = req.get("data", b"")

        logger.debug(f"Handling request: cmd={cmd}, data={data.hex()}")

        # ---- Universal commands ----
        if cmd == 0:
            # Структура відповіді (12 байт):
            # [0] 0xFE (Constant)
            # [1] Manuf ID (8 bit, pure)
            # [2] Device Type (8 bit)
            # [3] Min Preambles
            # [4] Univ Cmd Rev
            # [5] Dev Spec Rev
            # [6] Soft Rev
            # [7] Hard Rev
            # [8] Flags
            # [9-11] Device ID (24 bit serial number)
            
            payload = bytearray()
            payload.append(0xFE)
            payload.append(self.manuf_id) # Чистий ID (напр. 3E, а не BE)
            payload.append(self.dev_type)
            payload.append(self.min_preambles_required)
            payload.append(5) # Universal Rev 5
            payload.append(9) # Device Specific Rev
            payload.append(1) # Software Rev
            payload.append(1) # Hardware Rev
            payload.append(0) # Flags
            
            # Serial Number (3 bytes) - беремо з self.serial_number
            # Наприклад, для 10001 (0x002711) це буде [00, 27, 11]
            payload.append((self.serial_number >> 16) & 0xFF)
            payload.append((self.serial_number >> 8) & 0xFF)
            payload.append(self.serial_number & 0xFF)
            
            return self._response_core(start, cmd, bytes(payload))

        elif cmd == 1:
            pv, units = self.read_pv()
            payload = pack(">Bf", units & 0xFF, float(pv))
            return self._response_core(start, cmd, payload)

        elif cmd == 2:
            ma, perc = self.read_loop_current_and_percent()
            payload = pack(">fBf", float(ma), 0, float(perc))
            return self._response_core(start, cmd, payload)

        elif cmd == 3:
            ma, _perc = self.read_loop_current_and_percent()
            (sv, su), (tv, tu), (qv, qu) = self.read_sv_tv_qv()
            pv, pu = self.read_pv()

            payload = (
                pack(">f", float(ma))
                + pack(">Bf", pu & 0xFF, float(pv))
                + pack(">Bf", su & 0xFF, float(sv))
                + pack(">Bf", tu & 0xFF, float(tv))
                + pack(">Bf", qu & 0xFF, float(qv))
            )
            return self._response_core(start, cmd, payload)

        # Cmd 6: Write Polling Address
        elif cmd == 6:
            if len(data) >= 1:
                new_addr = data[0]
                # Оновлюємо адресу в пам'яті самого пристрою
                self.polling_address = new_addr
                # Повертаємо ехо (нову адресу)
                return self._response_core(start, cmd, bytes([new_addr]))
            else:
                return self._response_core(start, cmd, b"", status_bytes=(0x08, 0x00))

        elif cmd == 7:
            payload = bytes([self.polling_address & 0x3F, self.loop_current_enabled & 0x01])
            return self._response_core(start, cmd, payload)

        elif cmd == 8:
            payload = bytes([c & 0xFF for c in self.var_classes])
            return self._response_core(start, cmd, payload)

        elif cmd == 9:
            if not data:
                codes = [0]
            else:
                n = data[0]
                if len(data) < n + 1:
                    return self.error_response(start, cmd, HART_STATUS["INVALID_DATA"])
                codes = list(data[1 : 1 + n])

            out = bytearray()
            pv, pu = self.read_pv()
            (sv, su), (tv, tu), (qv, qu) = self.read_sv_tv_qv()
            for c in codes:
                if c == 0:
                    val, u = pv, pu
                elif c == 1:
                    val, u = sv, su
                elif c == 2:
                    val, u = tv, tu
                elif c == 3:
                    val, u = qv, qu
                else:
                    val, u = 0.0, 0
                status = 0x00 if self.lower_range <= val <= self.upper_range else 0x01
                out += bytes([status]) + pack(">fB", float(val), u & 0xFF)
            return self._response_core(start, cmd, bytes(out))

        elif cmd == 11:
            # Simulator-friendly behaviour:
            # Cmd 11 is "Read Unique Identifier Associated With Tag".
            # We validate the tag (plain ASCII, padded with spaces) and, if it matches,
            # return the same 4-byte header fields as shown in the Cmd11 UI block.
            req_tag = (data or b"").decode("ascii", errors="ignore").strip()
            dev_tag = (self.tag or "").strip()
            if req_tag and dev_tag and (req_tag != dev_tag):
                return self.error_response(start, cmd, HART_STATUS["INVALID_DATA"])

            payload = bytes(
                [
                    self.hart_major_rev,
                    self.min_preambles_required,
                    self.device_rev,
                    self.software_rev,
                ]
            )
            return self._response_core(start, cmd, payload)

        elif cmd == 12:
            msg = (self.message or "")[:24].ljust(24)
            payload = msg.encode("ascii", errors="ignore")
            return self._response_core(start, cmd, payload)

        elif cmd == 13:
            tag = (self.tag or "")[:8].ljust(8)
            desc = (self.descriptor or "")[:16].ljust(16)
            d, m, y = self.date
            payload = (
                tag.encode("ascii", errors="ignore")
                + desc.encode("ascii", errors="ignore")
                + bytes([d & 0xFF, m & 0xFF, (y >> 8) & 0xFF, y & 0xFF])
            )
            return self._response_core(start, cmd, payload)

        elif cmd == 14:
            # SIMULATOR FORMAT for UI fields:
            # payload = u32 serial + f32 upper + f32 lower + f32 min_span
            payload = pack(">Ifff", int(self.serial_number) & 0xFFFFFFFF, float(self.upper_range), float(self.lower_range), float(self.min_span))
            return self._response_core(start, cmd, payload)

        elif cmd == 15:
            # SIMULATOR FORMAT for UI fields:
            # payload = alarm(1) + transfer(1) + upper(f32) + lower(f32) + damping(f32) + write_protect(1)
            payload = bytes([self.alarm_code & 0xFF, self.transfer_code & 0xFF]) + pack(">fff", float(self.upper_range), float(self.lower_range), float(self.damping)) + bytes([self.write_protect & 0xFF])
            return self._response_core(start, cmd, payload)

        elif cmd == 16:
            payload = bytes(
                [
                    (self.serial_number >> 16) & 0xFF,
                    (self.serial_number >> 8) & 0xFF,
                    self.serial_number & 0xFF,
                ]
            )
            return self._response_core(start, cmd, payload)

        elif cmd == 17:
            # simulator: accept 24 ASCII bytes, store and ECHO back (so UI can show "actually used")
            txt = data[:24].decode("ascii", errors="ignore")
            self.message = txt
            self._touch_config_changed()
            echo = (self.message or "")[:24].ljust(24).encode("ascii", errors="ignore")
            return self._response_core(start, cmd, echo)

        elif cmd == 18:
            # simulator: request = 8(tag)+16(desc)+4(date)
            if len(data) < 28:
                return self.error_response(start, cmd, HART_STATUS["INVALID_DATA"])
            self.tag = data[0:8].decode("ascii", errors="ignore").strip()
            self.descriptor = data[8:24].decode("ascii", errors="ignore").strip()
            d = data[24]
            m = data[25]
            y = (data[26] << 8) | data[27]
            self.date = (d, m, y)
            self._touch_config_changed()
            # echo back
            tag = (self.tag or "")[:8].ljust(8)
            desc = (self.descriptor or "")[:16].ljust(16)
            echo = tag.encode("ascii", errors="ignore") + desc.encode("ascii", errors="ignore") + bytes([d & 0xFF, m & 0xFF, (y >> 8) & 0xFF, y & 0xFF])
            return self._response_core(start, cmd, echo)

        elif cmd == 19:
            if len(data) < 3:
                return self.error_response(start, cmd, HART_STATUS["INVALID_DATA"])
            self.serial_number = ((data[0] << 16) | (data[1] << 8) | data[2]) & 0xFFFFFF
            self.unique_id_str = f"{self.manuf_id:02X}{self.dev_type:02X}{self.serial_number:06X}"
            self._touch_config_changed()
            echo = bytes([(self.serial_number >> 16) & 0xFF, (self.serial_number >> 8) & 0xFF, self.serial_number & 0xFF])
            return self._response_core(start, cmd, echo)

        # ---- Additional (simulated) commands for your GUI ----
        elif cmd == 22:
            # Write long tag (simulator): 32 ASCII bytes, echo back
            if not isinstance(data, (bytes, bytearray)):
                return self.error_response(start, cmd, HART_STATUS["INVALID_DATA"])
            txt = data[:32].decode("ascii", errors="ignore").strip()
            self.long_tag = txt
            self._touch_config_changed()
            echo = (self.long_tag or "")[:32].ljust(32).encode("ascii", errors="ignore")
            return self._response_core(start, cmd, echo)

        elif cmd == 38:
            # Reset configuration changed flag (simulator): return previous counter (2 bytes) and reset to 0
            prev = int(self.config_change_counter) & 0xFFFF
            self.config_change_counter = 0
            payload = bytes([(prev >> 8) & 0xFF, prev & 0xFF])
            return self._response_core(start, cmd, payload)

        elif cmd == 48:
            # Read additional device status (SIMULATOR FORMAT): 10 bytes (one per GUI field)
            pv, _u = self.read_pv()
            out_of_range = int(not (self.lower_range <= pv <= self.upper_range))
            device_specific_1 = 0x00
            extended_field = 0x00
            operating_mode = 0x01  # normal
            std0 = 0x01 if out_of_range else 0x00
            std1 = 0x00
            analog_saturated = 0x01 if pv > self.upper_range else 0x00
            std2 = 0x00
            std3 = 0x00
            analog_fixed = 0x00
            device_specific_2 = 0x00
            payload = bytes([
                device_specific_1,
                extended_field,
                operating_mode,
                std0,
                std1,
                analog_saturated,
                std2,
                std3,
                analog_fixed,
                device_specific_2,
            ])
            return self._response_core(start, cmd, payload)

        return self.error_response(start, cmd, HART_STATUS["UNSUPPORTED_CMD"])
