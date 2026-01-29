from .base_slave import BaseSlave
import random
import time

class FlowSensor(BaseSlave):
    def __init__(self, polling_address, tag, model, manufacturer, serial_number):
        super().__init__(polling_address, tag, model, manufacturer, serial_number)
        
        self.upper_range = 100.0
        self.lower_range = 0.0
        
        self._base_pv = 55.0
        if polling_address == 7: self._base_pv = 52.0
        self.var_classes = [1, 0, 0, 0]
        
        # Змінні для лічильника (Totalizer)
        self._totalizer = 12345.67  # Початковий показник (м3)
        self._last_time = time.time()

    def read_pv(self):
        # PV: Flow Rate (m3/h)
        noise = random.uniform(-0.5, 0.5)
        val = float(self._base_pv + noise)
        self._cached_flow = val
        return val, 19  # Unit 19 = m3/h

    def read_sv_tv_qv(self):
        # Розрахунок часу, що пройшов
        now = time.time()
        dt = now - self._last_time
        self._last_time = now
        
        # SV: Totalizer (m3). Інтегруємо потік.
        # Flow (m3/h) * dt (sec) / 3600
        current_flow = getattr(self, "_cached_flow", 0.0)
        if current_flow > 0:
            self._totalizer += (current_flow * dt) / 3600.0
        
        # TV: Velocity (m/s). 
        # Припустимо трубу DN100. V = Flow / Area.
        # Для симуляції просто ділимо потік на коефіцієнт ~28
        velocity = current_flow / 28.3 
        
        # QV: Coil Drive Frequency/Current (Generic value ~37 Hz/mA)
        coil_val = 37.5 + random.uniform(-0.1, 0.1)

        # Unit 43 = m3 (Volume), Unit 21 = m/s (Velocity), Unit 38 = Hz
        return (self._totalizer, 43), (velocity, 21), (coil_val, 38)