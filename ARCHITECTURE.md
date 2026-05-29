# HART Protocol Simulator - Архітектура проекту

## 📋 Вступ

Це документація архітектури **HART Protocol Simulator** - симулятора HART протоколу, який дозволяє емулювати роботу пристроїв на HART шині та взаємодію з ними через графічний інтерфейс PyQt5.

**Дата розробки:** 2025
**Основні залежності:** PyQt5, pyserial, hart_protocol, python-dotenv

---

## 🏗️ Загальна архітектура

```
┌─────────────────────────────────────────────────────────┐
│           Графічний інтерфейс (GUI)                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Window.py (HARTWindow) - головне вікно         │   │
│  │  GUIv2.py (Ui_HARTAnalyzer) - сгенерований UI  │   │
│  └─────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────┘
                   │ керує
                   ▼
┌─────────────────────────────────────────────────────────┐
│        Контролер (Controller Layer)                     │
│  ┌─────────────────────────────────────────────────┐   │
│  │  HARTBusController - основний контролер         │   │
│  │  CommandHandler - обробка команд                │   │
│  └─────────────────────────────────────────────────┘   │
└──────────┬──────────────────────────────┬────────────────┘
           │ керує                        │ керує
           ▼                              ▼
    ┌────────────────┐           ┌─────────────────┐
    │  HART Master   │           │   HART Bus      │
    │                │◄─────────►│                 │
    │ Будує запити   │ отправля  │ Маршрутизує     │
    │                │ отримує   │ Имітує затримк │
    └────────────────┘           └────────┬────────┘
           │                               │
           │ відправляє запити             │ управляє
           │ та отримує відповіді           │
           │                              ▼
           │                  ┌─────────────────────────┐
           │                  │  HART Bus Devices       │
           │                  │ (Slaves / Sensors)      │
           │                  │                         │
           │                  │ • LevelSensor          │
           │                  │ • FlowSensor           │
           │                  │ • TemperatureSensor    │
           │                  │ • PHSensor             │
           │                  │ • TransparencySensor   │
           │                  └─────────────────────────┘
           │
           ▼
    ┌────────────────────────────┐
    │  Message Parser            │
    │  • Парсер HART фреймів     │
    │  • Побудовник фреймів      │
    │  • Обчислення checksum     │
    └────────────────────────────┘
```

---

## 📝 Опис ключових компонентів

### 1. **main.py** - Точка входу

**Розташування:** `src/main.py`

**Відповідальність:**
- Ініціалізація PyQt5 додатку
- Створення головного вікна (HARTWindow)
- Ініціалізація контролера HART шини (HARTBusController)
- Запуск основного циклу додатку

**Залежності:**
```
main.py
├── PyQt5 (QtWidgets)
├── gui/Window.py (HARTWindow)
└── controllers/hart_bus_controller.py (HARTBusController)
```

**Код:**
```python
def main():
    app = QtWidgets.QApplication(sys.argv)
    main_window = HARTWindow()
    bus_controller = HARTBusController(main_window)
    
    main_window.show()
    sys.exit(app.exec_())
```

---

### 2. **GUI Layer** - Графічний інтерфейс

#### **Window.py** - Головне вікно
**Розташування:** `src/gui/Window.py`

**Клас:** `HARTWindow(QtWidgets.QMainWindow)`

**Відповідальність:**
- Утримує весь UI визначений у GUIv2.py
- Керує додатковими елементами керування (Runtime options):
  - Control checkbox - битовий декодинг логів
  - Frame format radio buttons - вибір формату (Short/Long)
  - Sim delay spinbox - затримка симуляції (мс)
- Управління кнопками збереження/завантаження логів
- Очищення полів даних
- Фільтрування логів

**Ключові методи:**
- `randomizeNumberOfPreambles()` - генерація випадкової кількості преамбул
- `onSaveLog()` - збереження логів у файл
- `onLoadSendData()` - завантаження даних з файлу
- `onClear()` - очищення текстових полів
- `changeControlCheckBox()` - обробка зміни статусу декодування

**Залежності:**
```
Window.py
├── PyQt5 (QtCore, QtGui, QtWidgets)
├── gui/GUIv2.py (Ui_HARTAnalyzer)
└── Файлова система (themes, логи)
```

#### **GUIv2.py** - Сгенерований UI
**Розташування:** `src/gui/GUIv2.py`

**Клас:** `Ui_HARTAnalyzer`

**Відповідальність:**
- Сгенерований файл (вірогідно з Qt Designer)
- Утримує всі визначення UI елементів:
  - Вкладки (tabs) для різних функцій
  - Текстові поля для логів (send_data, raw_data, decrypted_data)
  - Таблиця пристроїв на шині
  - Поля введення адреси та ID пристрою
  - Кнопки для керування

**Не редагується вручну** (слід регенерувати з Qt Designer при змінах)

---

### 3. **Controller Layer** - Контролери

#### **hart_bus_controller.py** - Основний контролер
**Розташування:** `src/controllers/hart_bus_controller.py`

**Клас:** `HARTBusController(QtCore.QObject)`

**Відповідальність:**
- **Сканування HART шини** - пошук всіх пристроїв
- **Управління таблицею пристроїв** - відображення результатів сканування
- **Керування обраним пристроєм** - синхронізація UI полів
- **Обробка користувацьких команд** - відправлення команд до пристроїв
- **Логування** - вивід інформації в текстові поля GUI

**Ключові атрибути:**
- `main_window` - посилання на HARTWindow
- `bus` - імітована HART шина (HARTBus)
- `master` - майстер протоколу (HARTMaster)
- `table` - таблиця пристроїв
- `control_checkbox` - прапор для декодування
- `device_address_hex`, `device_id_dec` - поля обраного пристрою
- `supported_commands` - словник доступних команд

**Ключові методи:**
- `scan_hart_bus()` - сканування пристроїв
- `send_command(cmd_id)` - відправлення команди до пристрою
- `register_device_on_bus()` - реєстрація нового пристрою
- `move_device_address()` - переміщення пристрою на іншу адресу
- `_init_bus()` - ініціалізація шини з пристроями

**Залежності:**
```
hart_bus_controller.py
├── PyQt5 (QtWidgets, QtCore)
├── mai/master.py (HARTMaster)
├── mai/bus.py (HARTBus)
├── mai/message_parser.py
├── controllers/command_handler.py
├── hart_protocol (зовнішня бібліотека)
│   ├── universal (команди)
│   └── common (спільні структури)
└── devices/* (Sensor classes)
    ├── level_sensor.py
    ├── flow_sensor.py
    ├── temperature_sensor.py
    ├── ph_sensor.py
    └── transparency_sensor.py
```

#### **command_handler.py** - Обробник команд
**Розташування:** `src/controllers/command_handler.py`

**Функція:** `send_command_logic(controller, cmd: int)`

**Відповідальність:**
- **Побудова запиту** за обраної адреси та ID команди
- **Відправлення запиту** через HARTMaster
- **Обробка відповіді** від пристрою
- **Логування** запиту та відповіді з опціональним битовим декодингом
- **Оновлення UI** - виведення результатів в текстові поля

**Ключові функції всередині:**
- `parse_int()` - парсинг числа з рядка
- `get_selected_address()` - отримання адреси з таблиці або введення
- `control_enabled()` - перевірка статусу декодування
- Логування запиту та відповіді в GUI

**Залежності:**
```
command_handler.py
├── PyQt5 (QtWidgets)
├── struct
├── re (регулярні вирази)
└── mai/message_parser.py
```

---

### 4. **Protocol Layer** - HART протокол

#### **master.py** - HART Майстер
**Розташування:** `src/mai/master.py`

**Клас:** `HARTMaster`

**Відповідальність:**
- **Побудова HART фреймів** запитів від майстра
- **Управління форматом кадру** (Short/Long)
- **Управління преамбулами** (кількість 0xFF байтів)
- **Транзакція** - відправлення запиту та отримання відповіді

**Ключові атрибути:**
- `bus` - посилання на імітовану шину
- `frame_format` - "short" або "long"
- `bitwise_decode` - флаг для декодування
- `_preambles` - кількість преамбул (3-7)

**Ключові методи:**
- `set_frame_format(fmt)` - встановлення формату
- `set_preambles(n)` - встановлення кількості преамбул
- `build_request(polling_addr, command, data)` - побудова повного фрейму
- `transact(polling_addr, command, data)` - відправлення та отримання

**Структура фрейму:**
```
[Preambles (0xFF)][START][ADDRESS][COMMAND][BYTE_COUNT][DATA...][CHECKSUM]
```

**Залежності:**
```
master.py
├── mai/bus.py (HARTBus)
├── mai/message_parser.py
│   ├── build_short_address()
│   ├── build_long_address()
│   ├── compute_checksum()
│   └── START_SHORT, START_LONG
```

#### **bus.py** - HART Шина (Симулятор)
**Розташування:** `src/mai/bus.py`

**Клас:** `HARTBus`

**Відповідальність:**
- **Реєстрація пристроїв** на шині
- **Маршрутизація запитів** до відповідних пристроїв
- **Імітація затримок** передачі
- **Сканування шини** - отримання списку всіх пристроїв
- **Управління адресами** пристроїв

**Ключові атрибути:**
- `delay_ms` - затримка симуляції
- `min_address`, `max_address` - діапазон адрес (0-63)
- `preambles` - кількість преамбул
- `_slaves` - словник зареєстрованих пристроїв

**Ключові методи:**
- `register_slave(addr, device)` - реєстрація пристрою
- `is_address_taken(addr)` - перевірка зайнятої адреси
- `move_slave(old_addr, new_addr)` - переміщення пристрою
- `scan_devices()` - отримання списку пристроїв
- `transact_frame(request)` - обробка запиту та повернення відповіді
- `_route_to_slave(addr)` - маршрутизація до пристрою

**Залежності:**
```
bus.py
├── threading (для синхронізації доступу)
├── time (для затримок)
├── mai/message_parser.py
│   ├── parse_request_frame()
│   ├── compute_checksum()
│   ├── verify_checksum()
│   └── START_SHORT, START_LONG
└── Devices (обробляють запити)
```

#### **message_parser.py** - Парсер HART повідомлень
**Розташування:** `src/mai/message_parser.py`

**Функції:**

| Функція | Відповідальність |
|---------|-----------------|
| `compute_checksum(core)` | Обчислює XOR checksum для фрейму |
| `verify_checksum(frame)` | Перевіряє коректність checksum |
| `build_short_address(addr)` | Формує коротку адресу (1 байт) |
| `build_long_address(unique_id)` | Формує довгу адресу (5 байт) |
| `parse_request_frame(frame)` | Парсує запит від майстра |
| `parse_response_frame(frame)` | Парсує відповідь від слейва |

**Константи:**
- `START_SHORT = 0x02` - розділювач для коротких фреймів
- `START_LONG = 0x82` - розділювач для довгих фреймів

**Залежності:**
```
message_parser.py
├── typing
├── struct (для упакування даних)
└── Немає зовнішніх залежностей
```

---

### 5. **Device Layer** - HART Пристрої (Слейви)

#### **base_slave.py** - Базовий клас слейва
**Розташування:** `src/devices/base_slave.py`

**Клас:** `BaseSlave`

**Відповідальність:**
- **Базова емуляція HART пристрою**
- **Обробка HART команд** (0, 1, 2, 3, 6, 11-19, 22, 38, 48)
- **Утримання параметрів пристрою** (tag, descriptor, message, тощо)
- **Управління PV (Primary Variable)** та іншими змінними

**Ключові атрибути:**
- `polling_address` - адреса на шині
- `unique_id_str` - унікальний ID пристрою
- `tag`, `descriptor`, `message` - текстові поля
- `model`, `manufacturer`, `serial_number` - інформація про пристрій
- `loop_current_enabled` - режим струму петлі
- `upper_range`, `lower_range` - діапазони значень
- `var_classes` - класи змінних для SV, TV, QV

**Ключові методи:**
- `read_pv()` - читання основної змінної
- `read_sv_tv_qv()` - читання додаткових змінних
- `process_command(cmd_id, data)` - обробка команди (виконує всі 48+ команд)

**HART команди що підтримуються:**
```
0  - Read Unique ID
1  - Read Primary Variable
2  - Read Loop Current and Percent
3  - Read Dynamic Variables
6  - Write Polling Address
11 - Read Unique ID by Tag
12 - Read Message
13 - Read Tag, Descriptor, Date
14 - Read PV Sensor Info
15 - Read Output Info
16 - Read Final Assembly Number
17 - Write Message
18 - Write Tag, Descriptor, Date
19 - Write Final Assembly Number
22 - Write Long Tag
38 - Reset Configuration Changed
48 - Read Additional Status
```

**Залежності:**
```
base_slave.py
├── logging
├── random
├── struct (pack)
├── typing
└── mai/message_parser.py (START_SHORT, START_LONG)
```

#### **Спеціалізовані сенсори** (Наслідування від BaseSlave)

**flow_sensor.py** - Датчик витрати
- **ПВ:** Витрата (м³/ч)
- **ДВ:** Лічильник об'єму (Totalizer)
- **ТВ:** Швидкість потоку (м/с)
- **КВ:** Частота (Hz)

**level_sensor.py** - Датчик рівня
- **ПВ:** Рівень рідини
- **Інші параметри:** залежить від реалізації

**temperature_sensor.py** - Датчик температури
- **ПВ:** Температура
- **Режимоване значення з випадковим шумом**

**ph_sensor.py** - Датчик pH
- **ПВ:** pH значення
- **Діапазон:** 0-14

**transparency_sensor.py** - Датчик прозорості
- **ПВ:** Прозорість (%)
- **Відсоток прозорості рідини**

---

## 📊 Потік даних

### Сценарій 1: Сканування шини

```
User Click "Scan Bus"
        │
        ▼
   HARTWindow
        │
        ▼
HARTBusController.scan_hart_bus()
        │
        ▼
   HARTBus.scan_devices()
        │
        ├─► Перебір всіх слейвів
        │   └─► Отримання: address, unique_id, device_id, model
        │
        ▼
   Оновлення таблиці UI
        └─► Виведення результатів в таблицю
```

### Сценарій 2: Відправлення команди

```
User Select Device + Click "Send Command"
        │
        ▼
HARTWindow
        │
        ▼
HARTBusController.send_command(cmd_id)
        │
        ▼
command_handler.send_command_logic()
        │
        ├─► Отримання адреси пристрою (таблиця або ввід)
        │
        ├─► HARTMaster.build_request()
        │   ├─► Преамбули (0xFF x N)
        │   ├─► START (0x02 або 0x82)
        │   ├─► ADDRESS
        │   ├─► COMMAND ID
        │   ├─► BYTE COUNT
        │   ├─► DATA
        │   └─► CHECKSUM (XOR)
        │
        ├─► HARTBus.transact_frame()
        │   ├─► Парсинг запиту
        │   ├─► Маршрутизація до слейва
        │   ├─► BaseSlave.process_command()
        │   │   └─► Генерація відповіді
        │   └─► Повернення відповіді
        │
        ├─► Логування запиту/відповіді
        │   ├─► Raw HEX формат
        │   └─► Опціональне битове декодування
        │
        ▼
   Оновлення текстових полів GUI
        └─► send_data_text_edit, raw_data_text_edit, декриптовані дані
```

---

## 🔄 Взаємодія компонентів

### Матриця залежностей

| Компонент | Залежить від | Використовується |
|-----------|-------------|-----------------|
| **main.py** | Window.py, HARTBusController | GUI стартап |
| **Window.py** | GUIv2.py, QtWidgets | UI контейнер |
| **GUIv2.py** | QtWidgets | UI дизайн |
| **HARTBusController** | HARTBus, HARTMaster, BaseSlave, command_handler | Основна логіка |
| **command_handler** | HARTMaster, message_parser | Обробка команд |
| **HARTMaster** | HARTBus, message_parser | Побудова фреймів |
| **HARTBus** | BaseSlave, message_parser | Маршрутизація |
| **message_parser** | Нічого | Утиліти |
| **BaseSlave** | message_parser | Обробка команд |
| **Сенсори** | BaseSlave | Спеціалізовані данні |

---

## 📂 Структура папок

```
Hartiks/
├── src/                         # Основний код
│   ├── main.py                 # Точка входу
│   ├── controllers/
│   │   ├── hart_bus_controller.py
│   │   └── command_handler.py
│   ├── gui/
│   │   ├── Window.py
│   │   └── GUIv2.py
│   ├── mai/                     # HART Master-Slave
│   │   ├── master.py           # HART Майстер
│   │   ├── bus.py              # Імітована шина
│   │   ├── message_parser.py   # Парсер фреймів
│   │   └── commands.py         # Команди (якщо є)
│   ├── devices/
│   │   ├── base_slave.py
│   │   ├── flow_sensor.py
│   │   ├── level_sensor.py
│   │   ├── temperature_sensor.py
│   │   ├── ph_sensor.py
│   │   └── transparency_sensor.py
│   └── themes/                  # Теми для GUI
│       └── modern_light_v2.qss
├── fhart/                       # HART протокол (wheel)
│   ├── hart_protocol-2023.6.0-py3-none-any.whl
│   └── README.md
├── themes/                      # Теми для GUI (видалено)
├── README.md
└── requirements.txt
```

---

## 🔍 Ключові файли та їхні ролі

| Файл | Роль | Тип |
|------|------|------|
| `main.py` | Точка входу програми | Entry Point |
| `Window.py` | Головне вікно GUI | UI Container |
| `hart_bus_controller.py` | Основна бізнес логіка | Controller |
| `command_handler.py` | Обробка команд | Handler |
| `master.py` | Побудова HART фреймів | Protocol |
| `bus.py` | Імітація HART шини | Simulator |
| `message_parser.py` | Парсинг HART протоколу | Protocol Utils |
| `base_slave.py` | Базовий HART слейв | Device Simulator |
| `*_sensor.py` | Спеціалізовані сенсори | Device Simulator |

---

## 🛠️ Типічні операції

### 1. Додавання нового сенсора

```python
# 1. Створити новий клас в devices/new_sensor.py
from .base_slave import BaseSlave

class NewSensor(BaseSlave):
    def __init__(self, polling_address, tag, model, manufacturer, serial_number):
        super().__init__(polling_address, tag, model, manufacturer, serial_number)
        # Налаштування
        
    def read_pv(self):
        # Повернення (значення, unit_code)
        return (value, unit)

# 2. Зареєструвати в HARTBusController._init_bus()
from devices.new_sensor import NewSensor
device = NewSensor(polling_address, tag, model, manufacturer, serial)
bus.register_slave(polling_address, device)
```

### 2. Додавання нової команди HART

```python
# В BaseSlave.process_command()
if cmd_id == 99:  # New command
    # Обробка команди
    return response_data
```

### 3. Зміна формату фрейму

Через GUI або програмно:
```python
master.set_frame_format("long")  # або "short"
```

---

## 📋 Залежності зовні (requirements.txt)

```
PyQt5                      # Графічний інтерфейс
pyserial                   # Комунікація через COM порти (якщо потрібна)
python-dotenv             # Конфігурація з .env
hart_protocol             # HART протокол (wheel у папці fhart/)
```

---

## 🎯 Висновки

Проект використовує **класичну 3-рівневу архітектуру**:

1. **GUI Layer** (PyQt5) - Взаємодія з користувачем
2. **Controller Layer** - Бізнес логіка та управління
3. **Protocol/Device Layer** - Емуляція HART протоколу та пристроїв

**main.py** є точкою входу, яка ініціалізує весь ланцюжок: GUI → Controller → Protocol → Devices.

Всі компоненти слабо пов'язані (loose coupling) і можуть бути розширювані без змін до іншіх компонентів.

