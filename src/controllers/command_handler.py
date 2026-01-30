from PyQt5 import QtWidgets
import struct
import re

try:
    from mai.message_parser import parse_response_frame
except Exception:
    parse_response_frame = None


def send_command_logic(controller, cmd: int):
    """Build request for selected device and command id, send, log and update UI."""

    # ---------- helpers ----------
    def parse_int(text: str):
        try:
            return int(text, 0)
        except Exception:
            m = re.search(r"\d+", text or "")
            return int(m.group(0)) if m else None

    def get_selected_address():
        # from table
        if getattr(controller, "table", None) is not None:
            try:
                row = controller.table.currentRow()
                if row >= 0:
                    item = controller.table.item(row, 0)
                    if item:
                        addr = parse_int((item.text() or "").strip())
                        if addr is not None:
                            return addr
            except Exception:
                pass

        # from manual field
        field = getattr(controller, "selected_addr_field", None)
        if isinstance(field, QtWidgets.QLineEdit):
            try:
                return parse_int((field.text() or "").strip())
            except Exception:
                pass

        return None

    def control_enabled():
        try:
            cb = getattr(controller, "control_checkbox", None)
            return bool(cb and cb.isChecked())
        except Exception:
            return False

    def warn(title, text):
        if hasattr(controller, "win"):
            QtWidgets.QMessageBox.warning(controller.win, title, text)
        elif hasattr(controller, "main_window"):
            QtWidgets.QMessageBox.warning(controller.main_window, title, text)

    def critical(title, text):
        if hasattr(controller, "win"):
            QtWidgets.QMessageBox.critical(controller.win, title, text)
        elif hasattr(controller, "main_window"):
            QtWidgets.QMessageBox.critical(controller.main_window, title, text)

    def notify(text: str, msec: int = 4000):
        try:
            if hasattr(controller, "_notify"):
                controller._notify(text, msec)
        except Exception:
            pass

    if cmd == 6:
        ui_temp = getattr(controller, "ui", None)
        # Просто читаємо число з поля. Якщо там число - відправляємо.
        if ui_temp:
            fld = getattr(ui_temp, "lineEdit_command6_new_address", None)
            if fld:
                txt = fld.text().strip()
                if not txt.isdigit():
                    QtWidgets.QMessageBox.warning(controller.win, "Error", "Enter a number (0-63)")
                    return

    # ---------- address ----------
    addr = get_selected_address()
    if addr is None:
        warn(
            "No device selected",
            "Please select a device in HART Bus Devices first (or enter address in Selected device field).",
        )
        return

    # ---------- data ----------
    data = b""
    try:
        cmd_data = controller._data_for_command(cmd)
    except Exception:
        cmd_data = b""

    # Commands that require user input
    if cmd_data is None and cmd in (6, 17, 18, 19, 22):
        warn("Input required", "Please provide required data for this command.")
        return

    if cmd_data:
        data = cmd_data

    # ---------- build ----------
    try:
        req = controller._build_request(addr, cmd, data)
    except Exception as e:
        critical("Build error", f"Cannot build request: {e}")
        return

    control_flag = control_enabled()

    # ---------- TX ----------
    try:
        controller._log_tx(req, control=control_flag)
    except Exception:
        pass

    # ---------- RX ----------
    try:
        resp = controller._send_on_bus(req, addr)
    except Exception as e:
        resp = b""
        critical("Bus error", f"Error during bus transmit: {e}")

    parsed = None
    if parse_response_frame and resp:
        try:
            parsed = parse_response_frame(resp)
        except Exception:
            parsed = None

    # Always log RX so the user sees something
    try:
        controller._log_rx(resp, parsed=parsed, control=control_flag)
    except Exception:
        pass

    # Feedback (status bar)
    if not resp:
        notify(f"Cmd {cmd}: no response")
    else:
        s1 = parsed.get("status1") if parsed else None
        s2 = parsed.get("status2") if parsed else None
        if s1 == 0 and s2 == 0:
            notify(f"Cmd {cmd}: OK")
        elif s1 is not None and s2 is not None:
            notify(f"Cmd {cmd}: device status {int(s1)&0xFF:02X} {int(s2)&0xFF:02X}")
        else:
            notify(f"Cmd {cmd}: response received")

    # ---------- last response ----------
    try:
        controller._update_last_response_ui(parsed)
    except Exception:
        pass

    # ---------- UI updates ----------
    ui = getattr(controller, "ui", None)
    if not parsed or ui is None:
        return

    cmd_id = parsed.get("command")
    payload = parsed.get("data", b"")
    if not isinstance(payload, (bytes, bytearray)):
        payload = b""

    try:
        # Cmd 0
        if cmd_id == 0 and len(payload) >= 7:
            # Major Rev -> Byte 4
            le = getattr(ui, "lineEdit_command0_rev_major", None)
            if le: le.setText(str(payload[4]))

            # Preambles -> Byte 3
            le = getattr(ui, "lineEdit_command0_preambles", None)
            if le: le.setText(str(payload[3]))

            # Device Rev -> Byte 5
            le = getattr(ui, "lineEdit_command0_dev_rev", None)
            if le: le.setText(str(payload[5]))

            # Software Rev -> Byte 6
            le = getattr(ui, "lineEdit_command0_sw_rev", None)
            if le: le.setText(str(payload[6]))

        # Cmd 1: >Bf (units, value)
        elif cmd_id == 1 and len(payload) >= 5:
            units, val = struct.unpack(">Bf", payload[:5])
            unit_names = {
                44: "m", 19: "m3/h", 32: "degC", 57: "%", 59: "pH"
            }
            unit_str = unit_names.get(units, str(units))
            le = getattr(ui, "lineEdit_command1_none", None)
            if le:
                le.setText(f"{val:.3f} {unit_str}")

        # Cmd 2: >fBf (mA, reserved, percent)
        elif cmd_id == 2 and len(payload) >= 9:
            ma, _r, perc = struct.unpack(">fBf", payload[:9])
            le1 = getattr(ui, "lineEdit_command2_ma", None)
            le2 = getattr(ui, "lineEdit_command2_percent", None)
            if le1: le1.setText(f"{ma:.3f}")
            if le2: le2.setText(f"{perc:.2f}")
        
        # Cmd 3: Loop Current + 4 Dynamic Variables
        elif cmd_id == 3:
            if len(payload) >= 24:
                try:
                    unpacked = struct.unpack(">fBfBfBfBf", payload[:24])
                    ma_val = unpacked[0]
                    
                    # --- FIX: Форматування (прибираємо "0" та "unused") ---
                    def fmt_var(unit_code, val):
                        if unit_code == 250: # Unused
                            return ""
                        if unit_code == 0:   # Dimensionless
                            return f"{val:.3f}"

                        unit_map = {
                            44: "m", 19: "m3/h", 32: "degC", 57: "%", 59: "pH", 
                            39: "mA", 40: "kOhm", 41: "Ohm", 43: "m3", 21: "m/s", 38: "Hz"
                        }
                        u_str = unit_map.get(unit_code, str(unit_code))
                        return f"{val:.3f} {u_str}"
                    # ------------------------------------------

                    # 1. Loop Current
                    le_ma = getattr(ui, "lineEdit_command3_ma", None)
                    if le_ma: le_ma.setText(f"{ma_val:.3f}")

                    # 2. PV
                    le_pv = getattr(ui, "lineEdit_command3_pv", None)
                    if le_pv: le_pv.setText(fmt_var(unpacked[1], unpacked[2]))

                    # 3. SV
                    le_sv = getattr(ui, "lineEdit_command3_sv", None)
                    if le_sv: le_sv.setText(fmt_var(unpacked[3], unpacked[4]))

                    # 4. TV
                    le_tv = getattr(ui, "lineEdit_command3_tv", None)
                    if le_tv: le_tv.setText(fmt_var(unpacked[5], unpacked[6]))

                    # 5. QV
                    le_qv = getattr(ui, "lineEdit_command3_qv", None)
                    if le_qv: le_qv.setText(fmt_var(unpacked[7], unpacked[8]))
                    
                except Exception as e:
                    print(f"[ERROR] Cmd 3 unpack error: {e}")

        # Cmd 6: Write Polling Address (RESPONSE)
        elif cmd_id == 6 and len(payload) >= 1:
            new_addr_resp = payload[0]
            
            # Просто виводимо результат
            le = getattr(ui, "lineEdit_command6_result", None)
            if le:
                le.setText(f"Set to {new_addr_resp}")
            
            print(f"[INFO] Address changed to {new_addr_resp}")
            
            # Пояснюємо користувачу (Тобі), що сталося
            if new_addr_resp > 0:
                print(" -> Device is now in MULTIDROP mode. Loop Current fixed at 4 mA.")
                print(" -> Values (PV) are still updating via Digital Communication!")
            else:
                print(" -> Device is in ANALOG mode. Loop Current is active.")

        # Cmd 11: Read Unique ID by Tag
        elif cmd_id == 11 and len(payload) >= 12:
            # Тепер ми отримуємо повну структуру (як в Cmd 0)
            # Байті змістилися: [4]=UnivRev, [3]=Preambles, [5]=DevRev, [6]=SwRev
            
            le = getattr(ui, "lineEdit_command11_resp_rev_major", None)
            if le: le.setText(str(payload[4]))

            le = getattr(ui, "lineEdit_command11_resp_preambles", None)
            if le: le.setText(str(payload[3]))

            le = getattr(ui, "lineEdit_command11_resp_dev_rev", None)
            if le: le.setText(str(payload[5]))

            le = getattr(ui, "lineEdit_command11_resp_sw_rev", None)
            if le: le.setText(str(payload[6]))

        # Cmd 12: message
        elif cmd_id == 12:
            msg = payload.decode("ascii", errors="ignore").rstrip()
            le = getattr(ui, "lineEdit_command12_message", None)
            if le: le.setText(msg)


        # Cmd 13: tag+desc+date
        elif cmd_id == 13 and len(payload) >= 28:
            tag = payload[0:8].decode("ascii", errors="ignore").strip()
            desc = payload[8:24].decode("ascii", errors="ignore").strip()
            day, month, yh, yl = payload[24], payload[25], payload[26], payload[27]
            year = (yh << 8) | yl
            le1 = getattr(ui, "lineEdit_command13_tag", None)
            le2 = getattr(ui, "lineEdit_command13_descriptor", None)
            le3 = getattr(ui, "lineEdit_command13_date", None)
            if le1: le1.setText(tag)
            if le2: le2.setText(desc)
            if le3: le3.setText(f"{year:04d}-{month:02d}-{day:02d}")

        # Cmd 14
        elif cmd_id == 14 and len(payload) >= 16:
            serial, upper, lower, minspan = struct.unpack(">Ifff", payload[:16])
            le_s = getattr(ui, "lineEdit_command14_pv_serial", None)
            le_u = getattr(ui, "lineEdit_command14_pv_upper_limit", None)
            le_l = getattr(ui, "lineEdit_command14_pv_lower_limit", None)
            le_m = getattr(ui, "lineEdit_command14_pv_min_span", None)
            if le_s: le_s.setText(str(serial))
            if le_u: le_u.setText(f"{upper:.3f}")
            if le_l: le_l.setText(f"{lower:.3f}")
            if le_m: le_m.setText(f"{minspan:.3f}")

        # Cmd 15
        elif cmd_id == 15 and len(payload) >= 15:
            alarm = payload[0]
            transfer = payload[1]
            upper, lower, damping = struct.unpack(">fff", payload[2:14])
            wp = payload[14]
            alarm_map = {0: "None", 1: "High", 2: "Low"}
            transfer_map = {0: "Linear", 1: "Sqrt"}
            le_a = getattr(ui, "lineEdit_command15_pv_alarm", None)
            le_t = getattr(ui, "lineEdit_command15_pv_transfer", None)
            le_u = getattr(ui, "lineEdit_command15_pv_upper_range", None)
            le_l = getattr(ui, "lineEdit_command15_pv_lower_range", None)
            le_d = getattr(ui, "lineEdit_command15_pv_dumping", None)
            le_wp = getattr(ui, "lineEdit_command15_write_protect", None)
            if le_a: le_a.setText(alarm_map.get(alarm, f"0x{alarm:02X}"))
            if le_t: le_t.setText(transfer_map.get(transfer, f"0x{transfer:02X}"))
            if le_u: le_u.setText(f"{upper:.3f}")
            if le_l: le_l.setText(f"{lower:.3f}")
            if le_d: le_d.setText(f"{damping:.3f}")
            if le_wp: le_wp.setText("ON" if wp else "OFF")

        # Cmd 16
        elif cmd_id == 16 and len(payload) >= 3:
            v = (payload[0] << 16) | (payload[1] << 8) | payload[2]
            le = getattr(ui, "lineEdit_command16_final_assembly_number", None)
            if le: le.setText(str(v))

        # Cmd 17
        elif cmd_id == 17:
            msg = payload.decode("ascii", errors="ignore").rstrip()
            le = getattr(ui, "lineEdit_command17_response_message", None)
            if le: le.setText(msg)

        # Cmd 18
        elif cmd_id == 18 and len(payload) >= 28:
            tag = payload[0:8].decode("ascii", errors="ignore").strip()
            desc = payload[8:24].decode("ascii", errors="ignore").strip()
            day, month, yh, yl = payload[24], payload[25], payload[26], payload[27]
            year = (yh << 8) | yl
            le = getattr(ui, "lineEdit_command18_response_tag_desc_date", None)
            if le: le.setText(f"{tag};{desc};{year:04d}-{month:02d}-{day:02d}")

        # Cmd 19
        elif cmd_id == 19 and len(payload) >= 3:
            v = (payload[0] << 16) | (payload[1] << 8) | payload[2]
            le = getattr(ui, "lineEdit_command19_response_final_assembly_number", None)
            if le: le.setText(str(v))

        # Cmd 22
        elif cmd_id == 22:
            txt = payload.decode("ascii", errors="ignore").rstrip()
            le = getattr(ui, "lineEdit_command22_response_long_tag", None)
            if le: le.setText(txt)

        # Cmd 38
        elif cmd_id == 38 and len(payload) >= 2:
            counter = (payload[0] << 8) | payload[1]
            le = getattr(ui, "lineEdit_command38_config_change_counter", None)
            if le: le.setText(str(counter))

        # Cmd 48
        elif cmd_id == 48 and len(payload) >= 10:
            names = [
                "lineEdit_command48_device_specific_status_1",
                "lineEdit_command48_extended_field_device_status",
                "lineEdit_command48_device_operating_mode",
                "lineEdit_command48_standardized_status_0",
                "lineEdit_command48_standardized_status_1",
                "lineEdit_command48_analog_channel_saturated",
                "lineEdit_command48_standardized_status_2",
                "lineEdit_command48_standardized_status_3",
                "lineEdit_command48_analog_channel_fixed",
                "lineEdit_command48_device_specific_status_2",
            ]
            for b, nm in zip(payload[:10], names):
                le = getattr(ui, nm, None)
                if le: le.setText(f"0x{int(b)&0xFF:02X}")

    except Exception:
        pass

    # ---------- refresh preambles UI ----------
    try:
        controller.win.randomizeNumberOfPreambles()
    except Exception:
        pass
