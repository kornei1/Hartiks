from .base_slave import BaseSlave
import random

class LevelSensor(BaseSlave):
    def __init__(self, polling_address, tag, model, manufacturer, serial_number):
        super().__init__(polling_address, tag, model, manufacturer, serial_number)
        
        self.upper_range = 6.0
        self.lower_range = 0.0
        
        # Висота монтажу (від дна до фланця датчика)
        self._mounting_height = 6.5 
        
        # Базові налаштування симуляції рівня
        self._tank_height = 6.0 
        self._base_level = 2.0 + (polling_address * 0.5) 
        if self._base_level > 5.5: self._base_level = 3.5
        
        self.var_classes = [2, 0, 0, 0]

    def read_pv(self):
        # PV: Рівень (m)
        noise = random.uniform(-0.005, 0.005)
        current_val = self._base_level + noise
        current_val = max(0.0, min(self._tank_height, current_val))
        
        # Кешуємо значення, щоб SV (Distance) було синхронізоване з PV (Level)
        self._cached_pv = current_val 
        return float(current_val), 44  # Unit 44 = m

    def read_sv_tv_qv(self):
        # SV: Distance (m). Фізика: Distance = Mounting Height - Level
        dist = self._mounting_height - getattr(self, "_cached_pv", 0.0)
        dist = max(0.0, dist)
        
        # TV: Electronics Temperature (degC). Трохи гріється.
        elec_temp = 28.0 + random.uniform(-0.5, 0.5)
        
        # QV: Signal Amplitude (dB). Сила ехо-сигналу.
        # Гарний сигнал ~50-60 dB. 
        # Unit 0 (безрозмірний або dB, якщо підтримується, але 0 безпечніше для демо)
        amp = 55.0 + random.uniform(-2.0, 2.0)
        
        return (dist, 44), (elec_temp, 32), (amp, 0)