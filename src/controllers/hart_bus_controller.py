# src/controllers/hart_bus_controller.py
from PyQt5 import QtWidgets, QtCore
from typing import Optional, Any, List
from functools import partial
import binascii
import struct
import re
import random
import os
import sys

# Try to import external hart_protocol library (wheel is included in ../fhart)
try:
    import hart_protocol
    from hart_protocol import universal, common
except ModuleNotFoundError:
    _ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    _WHL = os.path.join(_ROOT, "fhart", "hart_protocol-2023.6.0-py3-none-any.whl")
    if os.path.isfile(_WHL) and _WHL not in sys.path:
        sys.path.insert(0, _WHL)
    import hart_protocol
    from hart_protocol import universal, common
from .command_handler import send_command_logic

SUPPORTED_COMMANDS = {
    0: "Read Unique ID",
    1: "Read Primary Variable",
    2: "Read Loop Current and Percent",
    3: "Read Dynamic Variables",
    6: "Write Polling Address",
    11: "Read Unique ID by Tag",
    12: "Read Message",
    13: "Read Tag, Descriptor, Date",
    14: "Read PV Sensor Info",
    15: "Read Output Info",
    16: "Read Final Assembly Number",
    17: "Write Message",
    18: "Write Tag, Descriptor, Date",
    19: "Write Final Assembly Number",
    22: "Write Long Tag",
    38: "Reset Configuration Changed",
    48: "Read Additional Status",
}



# core protocol / bus / master (можуть бути різні реалізації у твоєму проєкті)
try:
    from mai.message_parser import parse_response_frame, parse_request_frame
except Exception:
    parse_response_frame = None
    parse_request_frame = None

try:
    from mai.master import HARTMaster
except Exception:
    HARTMaster = None

try:
    from mai.bus import HARTBus
except Exception:
    HARTBus = None

# devices
from devices.level_sensor import LevelSensor
from devices.flow_sensor import FlowSensor
from devices.transparency_sensor import TransparencySensor
from devices.temperature_sensor import TemperatureSensor
try:
    from devices.ph_sensor import PHSensor as PhSensorClass
except Exception:
    try:
        from devices.ph_sensor import PhSensor as PhSensorClass
    except Exception:
        PhSensorClass = None

# simple logger helper (append to QTextEdit(s))
def _hex(b: bytes) -> str:
    return ''.join(f"{x:02X}" for x in b)

def _append_text(widget: Optional[QtWidgets.QTextEdit], text: str):
    if widget is None:
        print(text, end="")
        return
    try:
        widget.append(text)
        # autoscroll
        try:
            sb = widget.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:
            pass
    except Exception:
        try:
            widget.insertPlainText(text + "\n")
        except Exception:
            print(text)

class HARTBusController(QtCore.QObject):
    """
    Контролер HART шини:
     - сканує шину і заповнює таблицю
     - керує Selected device полями
     - прив'язує і відсилає Universal Commands (через master/bus)
     - логує TX/RX у UI
    """

    def __init__(self, main_window: Any):
        super().__init__(main_window)
        self.win = main_window
        # ui можливо в main_window.ui (згенерований клас) або безпосередньо в main_window
        self.ui = getattr(self.win, "ui", None)

        # --- допоміжник для пошуку віджета --- (спробуємо кілька йменувань)
        def find_widget(candidates: List[str]):
            for nm in candidates:
                # через ui
                if self.ui is not None:
                    w = getattr(self.ui, nm, None)
                    if w is not None:
                        return w
                # напряму у головному вікні
                w = getattr(self.win, nm, None)
                if w is not None:
                    return w
            return None

        # --- знайдемо основні віджети (в UIv001.py імена такі) ---
        self.table = find_widget(["founded_devices_table", "tableWidget_founded_devices", "foundedDevicesTable"])
        self.scan_button = find_widget(["scan_bus_button", "pushButton_scan_bus", "btnScanBus"])
        self.clear_button = find_widget(["clear_table_button", "pushButton_clear_table", "btnClearTable"])
        self.settings_button = find_widget(["scan_settings_button", "pushButton_scan_settings", "btnScanSettings"])

        # selected device display fields (реальні імена у GUIv001.py)
        self.selected_addr_field = find_widget([
            "device_address_hex", "device_address_hex_lineEdit", "lineEdit_selected_device_address",
            "lineEdit_selected_device_address", "lineEdit_device_address_hex"
        ])
        self.selected_id_field = find_widget([
            "device_id_dec", "device_id_dec_lineEdit", "lineEdit_selected_device_id",
            "lineEdit_device_id"
        ])

        # лог/журнал поля
        self.raw_log_widget = find_widget(["raw_data_text_edit", "rawDataTextEdit", "raw_data_textedit"])
        self.decrypted_log_widget = find_widget(["decrypted_data_text_edit", "decryptedDataTextEdit"])
        self.send_data_widget = find_widget(["send_data_text_edit", "sendDataTextEdit", "send_data_textedit"])

        # верхні Last response поля
        self.last_cmd = find_widget(["last_command_edit", "lineEdit_last_command", "lineEdit_lastCmd"])
        self.last_bc = find_widget(["last_data_field_size_edit", "lineEdit_last_bc", "lineEdit_lastByteCount"])
        self.last_s1 = find_widget(["last_status1_edit", "lineEdit_last_s1"])
        self.last_s2 = find_widget(["last_status2_edit", "lineEdit_last_s2"])

        # widgets controlling frame/preambles/delay (try many names)
        self.preambles_widget = find_widget(["num_preambles_edit", "preambles_spin", "spinBox_preambles", "spinBox_preambles", "lineEdit_num_preambles"])
        self.delay_widget = find_widget(["delay_spinbox", "spinBox_delay", "spinBoxDelay"])

        # control checkbox for bitwise decode
        self.control_checkbox = find_widget(["control_checkbox", "checkBox_control", "checkBoxControl"])

        # --- init bus & master (tolerant) ---
        try:
            delay_ms = int(self.delay_widget.value()) if hasattr(self.delay_widget, "value") else 200
        except Exception:
            delay_ms = 200

        # create bus/master only if classes available; if not, set to None and still allow UI to function
        try:
            self.bus = HARTBus(delay_ms=delay_ms) if HARTBus is not None else None
        except Exception:
            self.bus = None

        try:
            self.master = HARTMaster(self.bus, frame_format="short", bitwise_decode=False) if HARTMaster is not None else None
        except Exception:
            self.master = None

        # set preambles if exists
        if self.bus and self.preambles_widget is not None:
            try:
                val = int(self.preambles_widget.value()) if hasattr(self.preambles_widget, "value") else int(self.preambles_widget.text())
                self.bus.set_preambles(val)
                if self.master and hasattr(self.master, "set_preambles"):
                    self.master.set_preambles(val)
            except Exception:
                pass

        # --- register demo slaves into bus (if bus present) ---
        if self.bus:
            self._register_default_slaves()

        # --- connect scan/clear/settings buttons ---
        if self.scan_button:
            try:
                self.scan_button.clicked.connect(self.scan_bus)
            except Exception:
                pass
        if self.clear_button:
            try:
                self.clear_button.clicked.connect(self.clear_table)
            except Exception:
                pass
        if self.settings_button:
            try:
                self.settings_button.clicked.connect(self.show_scan_settings)
            except Exception:
                pass

        # connect table selection
        if self.table:
            try:
                self.table.itemSelectionChanged.connect(self._on_table_selection)
            except Exception:
                pass

        # if the Selected Device address field is editable, allow manual input
        if isinstance(self.selected_addr_field, QtWidgets.QLineEdit):
            try:
                self.selected_addr_field.editingFinished.connect(self._on_selected_addr_edited)
            except Exception:
                try:
                    self.selected_addr_field.textChanged.connect(self._on_selected_addr_text_changed)
                except Exception:
                    pass

        # bind send-command buttons dynamically (find names in UI file)
        # expected objectNames: send_command0_button, send_command1_button, ...
        self._bind_send_buttons()

        # initial scan (populate table)
        try:
            self.scan_bus()
        except Exception:
            pass

        # keep current selected address
        self.selected_address: Optional[int] = None

        # Update Bus button
        self.ui.updateBusButton.clicked.connect(self.UpdateBusButtonClicked)
        
        # --- NEW: Підключаємо радіо-кнопки формату кадру ---
        # Знаходимо їх через win, бо вони створені динамічно у Window.py
        self.rb_short = getattr(self.win, "frame_short_radio", None)
        self.rb_long = getattr(self.win, "frame_long_radio", None)

        if self.rb_short:
            self.rb_short.toggled.connect(self._on_frame_format_changed)
        if self.rb_long:
            self.rb_long.toggled.connect(self._on_frame_format_changed)
            
        # Застосуємо початковий стан
        self._on_frame_format_changed()
        # ----------------------------------------------------

        # --- NEW: Метод обробки перемикача Short/Long ---
    def _on_frame_format_changed(self):
        if not self.master:
            return
        
        is_short = False
        if self.rb_short and self.rb_short.isChecked():
            is_short = True
            
        # Передаємо налаштування у Master
        # (Переконайся, що у master.py є метод set_frame_format, він там був у твоєму файлі)
        fmt = "short" if is_short else "long"
        try:
            self.master.set_frame_format(fmt)
        except Exception:
            pass
    # ------------------------------------------------

        # Manual packet sender (Logs tab): add SEND button + Shift+Enter
        self._setup_manual_send_controls()
    
    """Re-scan bus button handler"""
    def UpdateBusButtonClicked(self):
        self.scan_bus()

    # ---------------- manual packets (Logs tab) ----------------
    def _setup_manual_send_controls(self):
        """Add a SEND button for manual packets and enable Shift+Enter in the editor."""
        ui = self.ui
        if ui is None:
            return

        self.manual_send_button = getattr(ui, "manual_send_button", None)
        # Create SEND button if it does not exist in .ui
        try:
            layout = getattr(ui, "send_data_buttons_layout", None)
            parent = getattr(ui, "send_data_group_2", None)
            if self.manual_send_button is None and layout is not None and parent is not None:
                btn = QtWidgets.QPushButton(parent)
                btn.setObjectName("manual_send_button")
                btn.setText("Send")
                # place it near Clear/Save/Load buttons
                layout.insertWidget(3, btn)
                self.manual_send_button = btn
                setattr(ui, "manual_send_button", btn)

            if self.manual_send_button is not None:
                self.manual_send_button.clicked.connect(self.send_manual_packet)
        except Exception:
            pass

        # Enable Shift+Enter send
        try:
            if self.send_data_widget is not None:
                self.send_data_widget.installEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            if obj is self.send_data_widget and event.type() == QtCore.QEvent.KeyPress:
                if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and (event.modifiers() & QtCore.Qt.ShiftModifier):
                    self.send_manual_packet()
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _notify(self, text: str, msec: int = 4000):
        """Lightweight user feedback: status bar + log."""
        try:
            self.win.statusBar().showMessage(text, msec)
        except Exception:
            pass

    def _parse_manual_hex(self, s: str):
        """Parse hex string like 'FF FF 82 ...' into bytes. Returns (bytes|None, error_msg|None)."""
        s = (s or "").strip()
        if not s:
            return None, "Empty input"

        # allow 0x prefix, commas, newlines
        cleaned = s.replace("0x", "").replace("0X", "")
        cleaned = "".join(ch for ch in cleaned if ch in "0123456789abcdefABCDEF")
        if len(cleaned) % 2 != 0:
            return None, "Hex string length must be even (2 chars per byte)."
        if not cleaned:
            return None, "No hex bytes found."
        try:
            return bytes.fromhex(cleaned), None
        except Exception:
            return None, "Invalid hex. Example: FF FF 82 80 00 00 00 01 0C 00 0F"

    def send_manual_packet(self):
        """Send a raw HART frame entered by the user (hex bytes) and show TX/RX."""
        if self.send_data_widget is None:
            return
        raw_text = self.send_data_widget.toPlainText() if hasattr(self.send_data_widget, "toPlainText") else ""
        frame, err = self._parse_manual_hex(raw_text)
        if frame is None:
            QtWidgets.QMessageBox.warning(self.win, "Manual send", f"Cannot send: {err}")
            return

        # update UI helpers if present
        try:
            chk = 0
            for b in frame:
                chk ^= b
            if getattr(self.ui, "current_string_crc", None):
                self.ui.current_string_crc.setText(f"{chk & 0xFF:02X}")
            if getattr(self.ui, "Byte_counter1", None) and self.ui.Byte_counter1.isChecked():
                if getattr(self.ui, "send_byte_counter", None):
                    self.ui.send_byte_counter.setText(str(len(frame)))
        except Exception:
            pass

        # send
        self._append_manual_tx(frame)
        resp = self._send_on_bus(frame, self.selected_address)
        parsed = None
        if parse_response_frame and resp:
            try:
                parsed = parse_response_frame(resp)
            except Exception:
                parsed = None
        self._log_rx(resp, parsed=parsed)

        if not resp:
            self._notify("Manual send: no response")
        else:
            s1 = parsed.get("status1") if parsed else None
            s2 = parsed.get("status2") if parsed else None
            ok = (s1 == 0 and s2 == 0) if (s1 is not None and s2 is not None) else True
            self._notify("Manual send: OK" if ok else f"Manual send: device returned status {s1:02X} {s2:02X}")

    def _append_manual_tx(self, frame: bytes):
        # --- FIX: Пишемо TX лог у вікно Send Data замість Raw Data ---
        _append_text(self.send_data_widget, f"TX (manual): ({len(frame)} bytes)")
        _append_text(self.send_data_widget, f"    Raw: {_hex(frame)}")

    def _register_default_slaves(self):
        # --- Real World Manufacturer IDs ---
        MANUF_VEGA = 0x3E      # Vega
        MANUF_ROSEMOUNT = 0x1A # Emerson/Rosemount
        MANUF_METTLER = 0x4A   # Mettler Toledo
        MANUF_EH = 0x11        # Endress+Hauser
        MANUF_SIEMENS = 0x2A   # Siemens
        
        # --- Real World Device Types (Example codes) ---
        TYPE_RADAR = 0xE9      # VEGAPULS
        TYPE_FLOW = 0x32       # Magnetic Flow
        TYPE_TURBIDITY = 0x10  # Generic
        TYPE_PH = 0x15         # Liquiline
        TYPE_TEMP = 0x06       # SITRANS TH300

        # register demo devices (15 total)
        # Unique ID calculated automatically in BaseSlave based on Manuf + Type + Serial
        
        # 5 Level Sensors (Vega)
        for i in range(1, 6):
            self.bus.register_slave(i, LevelSensor(i, f"LVL-00{i}", "VEGAPULS 64", "Vega", 10000 + i))
            # HACK: Force real IDs directly into the instance
            slave = self.bus._slaves[i]
            slave.manuf_id = MANUF_VEGA
            slave.dev_type = TYPE_RADAR
            slave.update_unique_id() # method we will add to BaseSlave

        # 2 Flow Sensors (Rosemount)
        for i in range(6, 8):
            self.bus.register_slave(i, FlowSensor(i, f"FLW-00{i}", "8732E", "Rosemount", 20000 + i))
            slave = self.bus._slaves[i]
            slave.manuf_id = MANUF_ROSEMOUNT
            slave.dev_type = TYPE_FLOW
            slave.update_unique_id()

        # 1 Transparency (Mettler Toledo)
        self.bus.register_slave(8, TransparencySensor(8, "TRS-001", "InPro 8000", "Mettler", 30001))
        self.bus._slaves[8].manuf_id = MANUF_METTLER
        self.bus._slaves[8].dev_type = TYPE_TURBIDITY
        self.bus._slaves[8].update_unique_id()

        # 3 pH Sensors (Endress+Hauser)
        if PhSensorClass:
            for i in range(9, 12):
                self.bus.register_slave(i, PhSensorClass(i, f"PH-00{i-8}", "Liquiline", "Endress+Hauser", 40000 + i, normal_range=(7.0, 7.0)))
                slave = self.bus._slaves[i]
                slave.manuf_id = MANUF_EH
                slave.dev_type = TYPE_PH
                slave.update_unique_id()

        # 4 Temperature Sensors (Siemens)
        for i in range(12, 16):
            self.bus.register_slave(i, TemperatureSensor(i, f"TEMP-00{i-11}", "SITRANS TH", "Siemens", 50000 + i))
            slave = self.bus._slaves[i]
            slave.manuf_id = MANUF_SIEMENS
            slave.dev_type = TYPE_TEMP
            slave.update_unique_id()

    # ---------------- scan / table ----------------
    def scan_bus(self):
        """Scan devices via bus.scan_devices() and populate table."""
        if not self.table:
            return
        devices = []
        if self.bus and hasattr(self.bus, "scan_devices"):
            try:
                devices = self.bus.scan_devices()
            except Exception:
                devices = []
        # ensure at least 4 columns exist
        try:
            if self.table.columnCount() < 4:
                self.table.setColumnCount(4)
        except Exception:
            pass

        self.table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            try:
                a = str(dev.get("address", ""))
                uid = str(dev.get("unique_id", ""))
                did = str(dev.get("device_id", ""))
                mm = f"{dev.get('model','')} / {dev.get('manufacturer','')}"
                self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(a))
                self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(uid))
                self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(did))
                self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(mm))
            except Exception:
                pass

        # select first row if any
        if self.table.rowCount() > 0:
            try:
                self.table.selectRow(0)
            except Exception:
                pass

    def clear_table(self):
        if not self.table:
            return
        try:
            self.table.setRowCount(0)
        except Exception:
            pass
        self.selected_address = None
        if isinstance(self.selected_addr_field, QtWidgets.QLineEdit):
            try:
                self.selected_addr_field.clear()
            except Exception:
                pass
        if isinstance(self.selected_id_field, QtWidgets.QLineEdit):
            try:
                self.selected_id_field.clear()
            except Exception:
                pass

    def show_scan_settings(self):
        if not self.bus:
            QtWidgets.QMessageBox.information(self.win, "Scan settings", "Bus not initialized.")
            return
        s = self.bus.get_settings() if hasattr(self.bus, "get_settings") else {}
        QtWidgets.QMessageBox.information(self.win, "Scan settings",
                                          f"Min: {s.get('min_address','?')}\nMax: {s.get('max_address','?')}\nDelay: {s.get('delay_ms','?')} ms\nPreambles: {s.get('preambles','?')}")

    # ---------------- table selection and selected device ----------------
    def _on_table_selection(self):
        """Update selected_address and top fields when user selects a row."""
        if not self.table:
            self.selected_address = None
            return
        items = self.table.selectedItems()
        if not items:
            self.selected_address = None
            # clear UI fields
            if isinstance(self.selected_addr_field, QtWidgets.QLineEdit):
                self.selected_addr_field.clear()
            if isinstance(self.selected_id_field, QtWidgets.QLineEdit):
                self.selected_id_field.clear()
            return

        # item 0 -> address, item 2 -> device id
        try:
            row = self.table.currentRow()
            addr_item = self.table.item(row, 0)
            did_item = self.table.item(row, 2)
            addr_text = addr_item.text() if addr_item else ""
            did_text = did_item.text() if did_item else ""
        except Exception:
            addr_text = ""
            did_text = ""

        parsed_addr = None
        if isinstance(addr_text, str) and addr_text.strip() != "":
            t = addr_text.strip()
            try:
                parsed_addr = int(t, 0)  # support 0x prefix
            except Exception:
                m = re.search(r'\d+', t)
                if m:
                    try:
                        parsed_addr = int(m.group(0))
                    except Exception:
                        parsed_addr = None

        self.selected_address = parsed_addr
        # update top UI fields
        if isinstance(self.selected_addr_field, QtWidgets.QLineEdit):
            try:
                if self.selected_address is not None:
                    self.selected_addr_field.setText(str(self.selected_address)) # self.selected_addr_field.setText(hex(self.selected_address))
                else:
                    self.selected_addr_field.setText(str(addr_text))
            except Exception:
                pass
        if isinstance(self.selected_id_field, QtWidgets.QLineEdit):
            try:
                self.selected_id_field.setText(str(did_text))
            except Exception:
                pass

    # ---------------- manual input handling ----------------
    def _on_selected_addr_edited(self):
        self._process_manual_address_input()

    def _on_selected_addr_text_changed(self, _):
        # debounce: process after short delay
        QtCore.QTimer.singleShot(300, self._process_manual_address_input)

    def _process_manual_address_input(self):
        if not isinstance(self.selected_addr_field, QtWidgets.QLineEdit):
            return
        txt = (self.selected_addr_field.text() or "").strip()
        if not txt:
            return
        parsed = None
        try:
            parsed = int(txt, 0)
        except Exception:
            m = re.search(r'\d+', txt)
            if m:
                try:
                    parsed = int(m.group(0))
                except Exception:
                    parsed = None
        if parsed is None:
            return
        self.selected_address = parsed
        # try to select row in table
        if not self.table:
            return
        found = None
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if not it:
                continue
            cell = (it.text() or "").strip()
            try:
                val = int(cell, 0)
            except Exception:
                mm = re.search(r'\d+', cell)
                if mm:
                    try:
                        val = int(mm.group(0))
                    except Exception:
                        continue
                else:
                    continue
            if val == parsed:
                found = r
                break
        if found is not None:
            try:
                self.table.selectRow(found)
            except Exception:
                pass

    # ---------------- bind send buttons ----------------
    def _bind_send_buttons(self):
        """Bind send buttons and hide entire command blocks for unsupported commands."""

        def find_cmd_group(cmd_id: int):
            # Most groups are named command_<id>_group; command 3 is command3_group
            candidates = [f"command_{cmd_id}_group", f"command{cmd_id}_group"]
            if cmd_id == 3:
                candidates = ["command3_group"]
            for nm in candidates:
                w = getattr(self.ui, nm, None) if self.ui is not None else None
                if w is not None:
                    return w
            return None

        containers = [self.ui, self.win] if self.ui is not None else [self.win]
        found_buttons = {}

        for container in containers:
            if not hasattr(container, "findChildren"):
                continue
            try:
                for btn in container.findChildren(QtWidgets.QPushButton):
                    name = btn.objectName() or ""
                    m = re.search(r"^send_command(\d+)_button$", name)
                    if not m:
                        continue
                    cmd_id = int(m.group(1))
                    found_buttons.setdefault(cmd_id, btn)

                    grp = find_cmd_group(cmd_id)
                    if cmd_id not in SUPPORTED_COMMANDS:
                        # Hide whole command block, so UI does not show non-implemented commands.
                        try:
                            btn.hide()
                        except Exception:
                            pass
                        if grp is not None:
                            try:
                                grp.hide()
                            except Exception:
                                pass
                    else:
                        try:
                            btn.show()
                        except Exception:
                            pass
                        if grp is not None:
                            try:
                                grp.show()
                            except Exception:
                                pass
            except Exception:
                continue

        for cmd_id, btn in found_buttons.items():
            if cmd_id not in SUPPORTED_COMMANDS:
                continue
            try:
                btn.clicked.connect(partial(self.send_command, cmd_id))
            except Exception:
                pass
    # ---------------- core: build/send/parse ----------------
    # ---------------- core: build/send/parse ----------------
    def _build_request_via_lib(self, addr: int, cmd: int, data: bytes = b"") -> Optional[bytes]:
        """
        Build request using hart-protocol library.
        Returns bytes or None if command not supported/failed.
        """
        try:
            # Universal
            if cmd == 0:
                return universal.read_unique_identifier(addr)
            elif cmd == 1:
                return universal.read_primary_variable(addr)
            elif cmd == 2:
                return universal.read_loop_current_and_percent(addr)
            elif cmd == 3:
                return universal.read_dynamic_variables_and_loop_current(addr)
            elif cmd == 6:
                # data[0] is new address
                if len(data) >= 1:
                    return universal.write_polling_address(addr, data[0])
            elif cmd == 11:
                # Cmd 11 in our simulator is sent to the *selected device address*.
                # The upstream library also provides a "UID by Tag" helper that does NOT take an address
                # and ends up producing a long-frame with address ...00 (poll 0), which yields no response
                # on our simulated bus.
                # So we build the request explicitly for the selected address and include the tag as plain ASCII.
                # (Our simulated slaves validate tag and respond with the same 4-byte header as Cmd0.)
                tag_bytes = data if data else b""
                return hart_protocol.tools.pack_command(addr, command_id=11, data=tag_bytes)
            elif cmd == 12:
                return universal.read_message(addr)
            elif cmd == 13:
                return universal.read_tag_descriptor_date(addr)
            elif cmd == 14:
                return universal.read_primary_variable_information(addr)
            elif cmd == 15:
                return universal.read_output_information(addr)
            elif cmd == 16:
                return universal.read_final_assembly_number(addr)
            elif cmd == 17:
                # write message (24 bytes ASCII in our simulator)
                if data is not None:
                    return hart_protocol.tools.pack_command(addr, command_id=17, data=data)

            elif cmd == 18:
                # write tag+descriptor+date (8+16+4 bytes in our simulator)
                if data is not None and len(data) >= 28:
                    return hart_protocol.tools.pack_command(addr, command_id=18, data=data)

            elif cmd == 19:
                # write final assembly num (3 bytes int)
                if len(data) >= 3:
                    val = (data[0] << 16) | (data[1] << 8) | data[2]
                    return universal.write_final_assembly_number(addr, val)

            elif cmd == 22:
                # write long tag (32 bytes ASCII in our simulator)
                if data is not None:
                    return hart_protocol.tools.pack_command(addr, command_id=22, data=data)

            # Common
            elif cmd == 38:
                 return common.reset_configuration_changed_flag(addr)
            elif cmd == 48:
                 return common.read_additional_transmitter_status(addr)

        except Exception as e:
            print(f"Error building lib request for cmd {cmd}: {e}")
            pass
        return None

    def _build_request(self, addr: int, cmd: int, data: bytes = b"") -> bytes:
        """
        Build request using library or fallback, BUT force the correct Unique ID
        from the table if we are in Long Frame mode.
        ALSO: Tell the bus where to route the packet (routing hint).
        """
        # 1. Update Preambles from UI
        if self.preambles_widget is not None:
            try:
                val_text = self.preambles_widget.text() if hasattr(self.preambles_widget, "text") else str(self.preambles_widget.value())
                current_preambles = int(val_text)
                if self.bus: self.bus.set_preambles(current_preambles)
                if self.master and hasattr(self.master, "set_preambles"):
                    self.master.set_preambles(current_preambles)
            except Exception:
                pass

        # 2. Determine Mode & Search for Unique ID in Table
        is_long = (self.master and self.master.frame_format == "long")
        
        # --- FIX №2: Підказуємо шині, кому ми це шлемо (Routing Hint) ---
        # Це критично для Long Frame з реальними ID, бо шина не може вгадати polling addr з UniqueID
        if is_long and self.bus:
            self.bus._forced_polling_for_long = int(addr)
        # ----------------------------------------------------------------

        found_unique_id = None
        if is_long and self.table:
            # Шукаємо рядок у таблиці, де коротка адреса співпадає з addr
            for r in range(self.table.rowCount()):
                item_addr = self.table.item(r, 0) # Short Addr
                item_uid = self.table.item(r, 1)  # Unique ID
                if item_addr and item_uid:
                    try:
                        row_val = int(item_addr.text(), 0) & 0x0F
                        req_val = int(addr) & 0x0F
                        if row_val == req_val:
                            uid_str = item_uid.text().strip()
                            if len(uid_str) == 10: # 5 bytes = 10 hex chars
                                found_unique_id = bytes.fromhex(uid_str)
                                break
                    except Exception:
                        pass

        # 3. Try building via Library
        lib_req = self._build_request_via_lib(addr, cmd, data)

        # --- FIX №1: PATCH THE LIBRARY REQUEST ---
        if lib_req:
            # Scenario A: Library gave Long Frame (0x82), and we have a REAL Unique ID.
            if is_long and found_unique_id:
                try:
                    # Skip preambles
                    idx = 0
                    while idx < len(lib_req) and lib_req[idx] == 0xFF:
                        idx += 1
                    
                    # Check if it is Long Frame
                    if idx < len(lib_req) and lib_req[idx] == 0x82 and (idx + 1 + 5) < len(lib_req):
                        # Construct new address with Master Bit
                        new_addr = bytearray(found_unique_id)
                        new_addr[0] |= 0x80 
                        
                        # Rebuild Core
                        start_byte = bytes([lib_req[idx]])
                        # Cut out old address (5 bytes), keep the rest (Command, BC, Data...) without old Checksum
                        rest_of_packet = lib_req[idx + 1 + 5 : -1] 
                        
                        core = start_byte + new_addr + rest_of_packet
                        
                        # Recalculate Checksum
                        chk = 0
                        for b in core: chk ^= b
                        
                        return lib_req[:idx] + core + bytes([chk])
                except Exception:
                    pass 

            # Scenario B: User wants Short Frame, but Library gave Long (0x82).
            if not is_long:
                 try:
                    idx = 0
                    while idx < len(lib_req) and lib_req[idx] == 0xFF:
                        idx += 1
                    if idx < len(lib_req) and lib_req[idx] == 0x82:
                        if parse_request_frame:
                            parsed = parse_request_frame(lib_req)
                            if parsed:
                                payload = parsed.get("data", b"")
                                return self.master.build_request(addr, cmd, payload)
                 except Exception:
                    pass

            return lib_req

        # 4. Fallback (Manual Construction)
        if self.master is not None and hasattr(self.master, "build_request"):
            if is_long and found_unique_id:
                # Manual construction with Real Unique ID
                preambles_count = getattr(self.bus, "preambles", 5) if self.bus else 5
                preambles = b'\xFF' * preambles_count
                start = b'\x82'
                
                addr_b = bytearray(found_unique_id)
                addr_b[0] |= 0x80
                
                cmd_b = bytes([cmd & 0xFF])
                bc = bytes([len(data) & 0xFF])
                core = start + addr_b + cmd_b + bc + data
                
                chk = 0
                for b in core: chk ^= b
                return preambles + core + bytes([chk])
            
            return self.master.build_request(addr, cmd, data)

        return b""

    def _send_on_bus(self, req: bytes, addr: Optional[int]) -> bytes:
        """
        Send raw frame using whichever API is present:
        1) self.bus.transact_frame(req) -> returns raw response frame
        2) self.bus.send_to_slave(addr, req_bytes) -> returns raw response
        3) if bus not present, return b''.
        """
        if self.bus is None:
            return b""
        # prefer transact_frame
        if hasattr(self.bus, "transact_frame"):
            try:
                return self.bus.transact_frame(req)
            except Exception:
                pass
        # fallback send_to_slave: pass only logical address and payload
        if hasattr(self.bus, "send_to_slave") and addr is not None:
            try:
                return self.bus.send_to_slave(addr, req)
            except Exception:
                pass
        # else, no response
        return b""

    def _log_tx(self, req: bytes, control: bool = False):
        # Parse for display
        cmd_id = -1
        try:
             # Find first non-FF
             i = 0
             while i < len(req) and req[i] == 0xFF:
                 i += 1
             if i < len(req):
                 # [START][ADDR...][CMD]
                 start = req[i]
                 idx = i + 1
                 if start == 0x02: # Short
                     idx += 1 # Address byte
                 elif start == 0x82: # Long
                     idx += 5 # 5 bytes addr
                 
                 if idx < len(req):
                     cmd_id = req[idx]
        except Exception:
            pass

        cmd_name = SUPPORTED_COMMANDS.get(cmd_id, f"Command {cmd_id}")
        
        txt = f"TX: {cmd_name} ({len(req)} bytes)"
        
        # --- FIX: Пишемо TX лог у вікно Send Data замість Raw Data ---
        _append_text(self.send_data_widget, txt)
        _append_text(self.send_data_widget, f"    Raw: {_hex(req)}")

    def _log_rx(self, resp: bytes, parsed: Optional[dict] = None, control: bool = False):
        if not resp:
            _append_text(self.raw_log_widget, "RX: (empty)")
            return

        # raw
        _append_text(self.raw_log_widget, f"RX: ({len(resp)} bytes)")
        _append_text(self.raw_log_widget, f"    Raw: {_hex(resp)}")

        # parsed summary
        if parsed is None and parse_response_frame is not None:
            try:
                parsed = parse_response_frame(resp)
            except Exception:
                parsed = None

        if not parsed:
            return

        cmd_id = parsed.get("command")
        bc = parsed.get("byte_count")
        s1 = parsed.get("status1")
        s2 = parsed.get("status2")
        payload = parsed.get("data", b"")
        name = SUPPORTED_COMMANDS.get(cmd_id, f"Command {cmd_id}")
        _append_text(self.decrypted_log_widget, f"Parsed RX: {name} | BC={bc} | S1={s1 if s1 is not None else '??'} | S2={s2 if s2 is not None else '??'}")
        if isinstance(payload, (bytes, bytearray)) and payload:
            _append_text(self.decrypted_log_widget, f"    Payload: {_hex(payload)}")
    def _update_last_response_ui(self, parsed: Optional[dict]):
        if parsed is None:
            return
        try:
            if isinstance(self.last_cmd, QtWidgets.QLineEdit):
                self.last_cmd.setText(str(parsed.get("command", "")))
            if isinstance(self.last_bc, QtWidgets.QLineEdit):
                self.last_bc.setText(str(parsed.get("byte_count", "")))
            # У parse_response_frame статус винесено в status1/status2, а data = payload
            s1 = parsed.get("status1", None)
            s2 = parsed.get("status2", None)
            if s1 is None or s2 is None:
                raw_data = parsed.get("raw_data", b"")
                if isinstance(raw_data, (bytes, bytearray)) and len(raw_data) >= 2:
                    s1, s2 = raw_data[0], raw_data[1]
            if s1 is not None and s2 is not None:
                if isinstance(self.last_s1, QtWidgets.QLineEdit):
                    self.last_s1.setText(f"{int(s1)&0xFF:02X}")
                if isinstance(self.last_s2, QtWidgets.QLineEdit):
                    self.last_s2.setText(f"{int(s2)&0xFF:02X}")
        except Exception:
            pass

    # -------------------- command-specific data builders --------------------
    def _data_for_command(self, cmd: int) -> Optional[bytes]:
        """Read command-specific request data from UI fields.

        IMPORTANT: this function returns ONLY the DATA bytes (not full HART frame).
        """
        ui = self.ui
        if ui is None:
            return b""

        def _ascii_pad(s: str, n: int) -> bytes:
            b = (s or "").encode("ascii", errors="ignore")[:n]
            return b.ljust(n, b" ")

        try:
            # Cmd 6: Write polling address
            if cmd == 6:
                fld = getattr(ui, "lineEdit_command6_address", None)
                if fld and isinstance(fld, QtWidgets.QLineEdit):
                    txt = (fld.text() or "").strip()
                    if not txt:
                        return None
                    val = int(txt, 0)
                    return bytes([val & 0xFF])
                return None

            # Cmd 11: Read unique id by Tag (we pass tag as ASCII, 8 bytes in our simulator UI)
            if cmd == 11:
                fld = getattr(ui, "lineEdit_command11_tag", None)
                tag = (fld.text() if fld else "") or ""
                return _ascii_pad(tag.strip(), 8)

            # Cmd 17: Write message (24 bytes)
            if cmd == 17:
                fld = getattr(ui, "lineEdit_command17_request_message", None)
                msg = (fld.text() if fld else "") or ""
                if not msg.strip():
                    return None
                return _ascii_pad(msg, 24)

            # Cmd 18: Write Tag/Descriptor/Date (8+16+4)
            if cmd == 18:
                fld = getattr(ui, "lineEdit_command18_request_tag_desc_date", None)
                raw = (fld.text() if fld else "") or ""
                raw = raw.strip()
                if not raw:
                    return None

                # Accept formats:
                #   TAG
                #   TAG;DESC
                #   TAG;DESC;YYYY-MM-DD
                # separators: ; , |
                parts = [p.strip() for p in re.split(r"[;|,]", raw) if p.strip()]
                tag = parts[0] if len(parts) >= 1 else ""
                desc = parts[1] if len(parts) >= 2 else ""
                date_s = parts[2] if len(parts) >= 3 else ""

                # parse date
                import datetime as _dt
                d = _dt.date.today()
                if date_s:
                    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
                        try:
                            d = _dt.datetime.strptime(date_s, fmt).date()
                            break
                        except Exception:
                            pass

                date_bytes = bytes([d.day & 0xFF, d.month & 0xFF, (d.year >> 8) & 0xFF, d.year & 0xFF])
                return _ascii_pad(tag, 8) + _ascii_pad(desc, 16) + date_bytes

            # Cmd 19: Write final assembly number (3 bytes)
            if cmd == 19:
                fld = getattr(ui, "lineEdit_command19_request_final_assembly_number", None)
                txt = (fld.text() if fld else "") or ""
                if not txt.strip():
                    return None
                v = int(txt.strip(), 0) & 0xFFFFFF
                return bytes([(v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])

            # Cmd 22: Write long tag (32 bytes)
            if cmd == 22:
                fld = getattr(ui, "lineEdit_command22_request_long_tag", None)
                txt = (fld.text() if fld else "") or ""
                if not txt.strip():
                    return None
                return _ascii_pad(txt, 32)

        except Exception:
            return None

        return b""
    # -------------------- main public: send command --------------------
    def send_command(self, cmd: int):
        send_command_logic(self, cmd)