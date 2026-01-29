# HART Protocol Simulator

## Overview

**HART Protocol Simulator** is a graphical application for simulating and testing the HART protocol (Highway Addressable Remote Transducer). Implemented in Python using PyQt5, it allows:

- Scanning a virtual HART bus
- Managing remote devices (level, flow, temperature, pH, transparency sensors)
- Sending Universal Commands (HART protocol commands)
- Viewing transaction logs (TX/RX)
- Simulating complex interaction scenarios on the HART bus

## Features

### Main Capabilities

1. **Bus Scanning**
   - Automatic HART bus scanning
   - Detection of all registered devices
   - Display device information in a table

2. **Device Management**
   - Select device from table
   - Read current address and device ID
   - Support for short addresses (0-63)

3. **Command Sending**
   - Universal Commands (0-31 and extended)
   - Command parameterization via GUI
   - TX/RX operation logging

4. **Testing and Debugging**
   - View raw data (HEX format)
   - Decode protocol responses
   - Control preambles and delays
   - Choose frame format (short/long)

### Simulated Devices

- **LevelSensor** (5 devices) - level sensors
- **FlowSensor** (2 devices) - flow rate sensors
- **TransparencySensor** (1 device) - transparency sensor
- **PHSensor** (3 devices) - pH sensors
- **TemperatureSensor** (4 devices) - temperature sensors

**Total:** 15 virtual HART devices

## Architecture

```
HART2/
├── src/
│   ├── main.py                    # Application entry point
│   ├── gui/
│   │   ├── Window.py              # Main window
│   │   ├── GUIv2.py               # UI class (generated from .ui)
│   │   └── GUI.ui                 # Qt Designer file
│   ├── controllers/
│   │   ├── hart_bus_controller.py # Bus controller (main logic)
│   │   └── command_handler.py     # Command processor
│   ├── hart_protocol/
│   │   ├── bus.py                 # HART bus simulation
│   │   ├── master.py              # HART master (frame builder)
│   │   ├── message_parser.py      # Frame and checksum parser
│   │   ├── commands.py            # HART command definitions
│   │   └── slave_manager.py       # Slave manager
│   └── devices/
│       ├── base_slave.py          # Base device class
│       ├── level_sensor.py        # Level sensor
│       ├── flow_sensor.py         # Flow sensor
│       ├── temperature_sensor.py  # Temperature sensor
│       ├── ph_sensor.py           # pH sensor
│       └── transparency_sensor.py # Transparency sensor
├── themes/                        # Qt stylesheets (dark/light)
├── config/                        # Configuration files
├── docs/                          # Documentation
├── requirements.txt               # Project dependencies
└── venv39/                        # Python 3.9 virtual environment
```

## Dependencies

- **PyQt5** - GUI framework
- **pyqt5-plugins, pyqt5-tools** - Additional Qt tools
- **pyserial** - Serial port communication
- **python-dotenv** - Environment variables management

## Installation and Running

### Requirements
- Python 3.9+
- Windows, macOS, or Linux

### Installing Dependencies

```bash
# 1. Activate virtual environment
# On Windows:
venv39\Scripts\activate

# On macOS/Linux:
source venv39/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
```

### Running the Application

```bash
# With activated virtual environment:
python src/main.py
```

The main window will open with the title "HART Protocol Simulator".

## Usage

### Basic Workflow

1. **Run the application** - `python src/main.py`
2. **Scan the bus** - click "Scan Bus" button
3. **Select a device** - click on a row in the table
4. **Send a command** - click the button for the desired command
5. **View results** - check the logs in text fields

### HARTBusController

The main bus management class is located in [src/controllers/hart_bus_controller.py](src/controllers/hart_bus_controller.py).

**Key Methods:**

- `scan_bus()` - scan bus and populate device table
- `send_command(cmd)` - send HART command
- `_build_request(addr, cmd, data)` - create request frame
- `_send_on_bus(req, addr)` - send frame on bus
- `_update_last_response_ui(parsed)` - update UI with result

### GUI Elements

| Element | Name | Function |
|---------|------|----------|
| Table | `founded_devices_table` | List of devices on bus |
| Button | `scan_bus_button` | Scan the bus |
| Button | `clear_table_button` | Clear table |
| Field | `device_address_hex` | Selected device address |
| Field | `device_id_dec` | Selected device ID |
| Log | `raw_data_text_edit` | Raw data (HEX) |
| Log | `decrypted_data_text_edit` | Decoded data |
| Buttons | `send_command*_button` | Command buttons |

## HART Protocol

### Frame Structure (Short Frame)

```
[FF x N][START][ADDR][CMD][BC][DATA...][CHK]

- FF x N  : N preambles (breaks) - typically 5-16
- START   : 0x02 for short, 0x82 for long
- ADDR    : address (6 bit address + 2 bit control)
- CMD     : command number (0-31 universal, 32-127 common practice)
- BC      : byte count (data length)
- DATA    : payload (0-253 bytes)
- CHK     : checksum (XOR of all bytes from START)
```

### Universal Commands

- **CMD 0** - Read Unique Identifier (UID, manufacturer, model)
- **CMD 1** - Read PV (Primary Variable - current value)
- **CMD 2** - Read Current and Percentage of Range
- **CMD 3** - Read Dynamic Variables and Loop Current
- **CMD 6** - Write Polling Address
- **CMD 9** - Read Device Variables (variable slots)
- **CMD 17** - Write Message (24-byte message)
- **CMD 18** - Write Tag/Descriptor/Date
- **CMD 19** - Write Serial Number

Complete list in [src/hart_protocol/commands.py](src/hart_protocol/commands.py).

## Class Structure

### BaseSlave (Base Device)

```python
class BaseSlave:
    def __init__(self, polling_address, unique_id, model, manufacturer, serial_number):
        self.polling_address = polling_address
        self.unique_id_str = unique_id
        self.model = model
        self.manufacturer = manufacturer
        self.serial_number = serial_number
    
    def handle_command(self, command, data):
        # Handle HART command
        pass
```

All sensors inherit from `BaseSlave` and implement device-specific command logic.

### HARTBus

Simulates a HART bus with device registry and command routing.

**Methods:**
- `register_slave(address, device)` - register device
- `scan_devices()` - get list of all devices
- `transact_frame(request_frame)` - transmit frame on bus
- `send_to_slave(address, request)` - direct transmission

### HARTMaster

Builds and manages requests to devices.

**Methods:**
- `build_request(polling_addr, command, data)` - create frame
- `set_frame_format(fmt)` - select format (short/long)
- `set_preambles(n)` - set number of preambles

## Debugging

### Logging

The application logs all operations in text fields:

1. **Raw Data Log** - raw data in HEX format
2. **Decrypted Data Log** - decoded structures
3. **Send Data Log** - sent commands

### Error Checking

To identify syntax and logical errors, use:

```bash
# Syntax check
python -m py_compile src/main.py

# Run with debugging
python -m pdb src/main.py
```

## Extension and Modification

### Adding a New Device

1. Create a class in `devices/`:
```python
from devices.base_slave import BaseSlave

class MyCustomSensor(BaseSlave):
    def __init__(self, polling_address, unique_id, ...):
        super().__init__(polling_address, unique_id, ...)
    
    def handle_command(self, command, data):
        if command == 1:
            # Handle CMD 1
            return your_response_data
```

2. Register in `HARTBusController._register_default_slaves()`:
```python
self.bus.register_slave(16, MyCustomSensor(...))
```

### Adding a New Command

1. Add definition in [src/hart_protocol/commands.py](src/hart_protocol/commands.py)
2. Handle in device's `handle_command()` method
3. Add button in GUI (GUI.ui)
4. Parameterize in `HARTBusController._data_for_command()`

## Testing

Main test scenarios:

1. ✅ Bus scan and detection of all 15 devices
2. ✅ Device selection and reading its address/ID
3. ✅ Send CMD 0 (Read UID)
4. ✅ Send CMD 1 (Read PV)
5. ✅ Verify checksums
6. ✅ Check TX/RX logs

## Window Structure (GUI)

The main window contains:

- **Top panel**: Preamble control, frame format, delay
- **Scan area**: Device table, management buttons
- **Command area**: Universal Command buttons
- **Selected device area**: Address, ID, status
- **Logs area**: Raw data, decoded data, sent data
- **Response area**: Last command, BC, S1, S2, data

## Configuration Files

- **sonar-project.properties** - SonarQube analysis config
- **requirements.txt** - dependencies list
- **themes/*.qss** - Qt stylesheets (light/dark)

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'PyQt5'"
**Solution:** Install dependencies: `pip install -r requirements.txt`

### Issue: Theme not loading
**Solution:** Check path in `main.py` - should be `./themes/py_dracula_light.qss`

### Issue: Devices not appearing in table
**Solution:** Ensure `HARTBus` is initialized and devices are registered in `_register_default_slaves()`

## Possible Extensions

1. **Real port connection** - replace simulation with real COM port
2. **Advanced decoding** - detailed HART frame parsing
3. **Log export** - save logs to file
4. **Scenario generator** - test automation
5. **Statistics** - command frequency and error analysis

## Author and License

Developed as an educational project for a diploma thesis.

## Contact

For questions and suggestions, see `helper.txt` and `changes.txt` files.
