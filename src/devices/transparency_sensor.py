from .base_slave import BaseSlave
import random

class TransparencySensor(BaseSlave):
    def __init__(self, polling_address, tag, model, manufacturer, serial_number):
        super().__init__(polling_address, tag, model, manufacturer, serial_number)
        
        self.upper_range = 100.0
        self.lower_range = 0.0
        self._base_pv = 88.0
        self.var_classes = [0, 0, 0, 0]

    def read_pv(self):
        # PV: Transparency (%)
        noise = random.uniform(-0.5, 0.5)
        val = self._base_pv + noise
        val = max(0.0, min(100.0, val))
        return float(val), 57  # Unit 57 = %

    def read_sv_tv_qv(self):
        # SV: Raw Signal (nA - nanoAmps). Фотострум.
        # Чим прозоріше, тим більше світла, тим більше струм.
        # Нехай при 100% буде ~500 nA
        raw_signal = 500.0 * (self._base_pv / 100.0) + random.uniform(-2.0, 2.0)
        
        # TV: Temp (degC)
        temp = 20.0 + random.uniform(-0.5, 0.5)
        
        # Unit 39 = mA (але для nA стандартного коду в нас може не бути, 
        # візьмемо 39 і будемо вважати це "scaled signal")
        return (raw_signal, 39), (temp, 32), (0.0, 250)