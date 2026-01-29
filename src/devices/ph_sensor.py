from .base_slave import BaseSlave
import random

class PHSensor(BaseSlave):
    def __init__(self, polling_address, tag, model, manufacturer, serial_number, normal_range=(7.0, 7.0)):
        super().__init__(polling_address, tag, model, manufacturer, serial_number)
        
        self.upper_range = 14.0
        self.lower_range = 0.0
        self.normal_range = tuple(normal_range)
        self.var_classes = [0, 0, 0, 0]

    def read_pv(self):
        # PV: pH
        min_val, max_val = self.normal_range
        if min_val == max_val:
            base = min_val
            noise = random.uniform(-0.05, 0.05)
            val = base + noise
        else:
            base = random.uniform(min_val, max_val)
            noise = random.uniform(-0.02, 0.02)
            val = base + noise
        val = max(0.0, min(14.0, val))
        return float(val), 59  # Unit 59 = pH

    def read_sv_tv_qv(self):
        # SV: Process Temperature (degC). 
        # pH завжди міряється разом з температурою.
        proc_temp = 22.0 + random.uniform(-0.5, 0.5)
        
        # TV: Glass Impedance (MOhm). 
        # Імітуємо високий опір (наприклад, 120 МОм). 
        # Unit 164 (MOhm) може не бути в стандартній таблиці, беремо generic (або kOhm * 1000)
        # Використаємо kOhm (Unit 40) і значення 120,000 кОм
        glass_imp = 120000.0 + random.uniform(-500, 500)
        
        # QV: Reference Impedance (kOhm). 
        # Діагностика діафрагми. Норма ~20-50 кОм.
        ref_imp = 25.0 + random.uniform(-0.5, 0.5)
        
        # Unit 32 = degC, Unit 40 = kOhm
        return (proc_temp, 32), (glass_imp, 40), (ref_imp, 40)