from .base_slave import BaseSlave
import random

class TemperatureSensor(BaseSlave):
    def __init__(self, polling_address, tag, model, manufacturer, serial_number):
        super().__init__(polling_address, tag, model, manufacturer, serial_number)
        
        self.upper_range = 100.0
        self.lower_range = 0.0
        self._base_pv = 21.0
        self.var_classes = [0, 0, 0, 0]

    def read_pv(self):
        # PV: Temperature (degC)
        noise = random.uniform(-0.2, 0.2)
        val = self._base_pv + noise
        self._cached_temp = val
        return float(val), 32  # Unit 32 = degC

    def read_sv_tv_qv(self):
        # SV: Terminal/Electronics Temp (degC). 
        # Зазвичай трохи вище температури навколишнього середовища.
        elec_temp = 25.0 + random.uniform(-0.1, 0.1)
        
        # TV: Sensor Resistance (Ohm). 
        # Для Pt100 формула: R = 100 + 0.385 * T (приблизно)
        t = getattr(self, "_cached_temp", 20.0)
        resistance = 100.0 + (0.385 * t)
        
        # QV: Unused
        return (elec_temp, 32), (resistance, 41), (0.0, 250) # Unit 41 = Ohm