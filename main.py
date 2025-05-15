from machine import SoftI2C, Pin
from ssd1306 import SSD1306_I2C
from max30102 import MAX30102
from utime import sleep, ticks_ms, ticks_diff

MIN_SIGNAL = 5000
HEART_RATE_LOW = 50
HEART_RATE_HIGH = 120

i2c_oled = SoftI2C(scl=Pin(5), sda=Pin(4), freq=400000)
oled = SSD1306_I2C(128, 64, i2c_oled)

i2c_sensor = SoftI2C(scl=Pin(22), sda=Pin(21), freq=400000)
sensor = MAX30102(i2c=i2c_sensor)

red_led = Pin(25, Pin.OUT)
green_led = Pin(26, Pin.OUT)
buzzer = Pin(27, Pin.OUT)

oled.fill(0)
oled.text("Initializing...", 0, 0)
oled.show()

if sensor.i2c_address not in i2c_sensor.scan():
    oled.fill(0)
    oled.text("MAX30102 Error!", 0, 0)
    oled.show()
    raise OSError("MAX30102 not detected")

sensor.setup_sensor()
sensor.set_fifo_average(4)
sensor.set_sample_rate(200)
sensor.set_active_leds_amplitude(0x2F)

oled.fill(0)
oled.text("MAX30102 Ready", 0, 0)
oled.show()

def calculate_heart_rate(timestamps):
    beats = len(timestamps)
    if beats < 2:
        return 0
    duration_ms = ticks_diff(timestamps[-1], timestamps[0])
    if duration_ms > 0:
        heart_rate = (beats / duration_ms) * 60000
        return int(heart_rate)
    return 0

def calculate_spo2(red_values, ir_values):
    if len(red_values) < 10 or len(ir_values) < 10:
        return None
    mean_red = sum(red_values) / len(red_values)
    mean_ir = sum(ir_values) / len(ir_values)
    ac_red = sum(abs(x - mean_red) for x in red_values) / len(red_values)
    ac_ir = sum(abs(x - mean_ir) for x in ir_values) / len(ir_values)
    if ac_ir == 0:
        return None
    ratio = (ac_red / mean_red) / (ac_ir / mean_ir)
    spo2 = 110 - 25 * ratio
    if spo2 < 0 or spo2 > 100:
        return None
    return int(spo2)

prev_ir = 0
is_rising = False
ir_timestamps = []

red_buffer = []
ir_buffer = []

in_alert_state = False

try:
    while True:
        sensor.check()
        if sensor.available():
            red = sensor.pop_red_from_storage()
            ir = sensor.pop_ir_from_storage()

            if ir < MIN_SIGNAL:
                oled.fill(0)
                oled.text("Place finger", 0, 0)
                oled.show()
                red_led.value(1)
                green_led.value(0)
                buzzer.value(1)
                sleep(0.2)
                buzzer.value(0)
                ir_timestamps.clear()
                red_buffer.clear()
                ir_buffer.clear()
                prev_ir = 0
                is_rising = False
                in_alert_state = False
            else:
                current_ir = ir
                if current_ir > prev_ir:
                    is_rising = True
                elif is_rising and current_ir < prev_ir:
                    ir_timestamps.append(ticks_ms())
                    if len(ir_timestamps) > 10:
                        ir_timestamps.pop(0)
                    is_rising = False
                prev_ir = current_ir

                red_buffer.append(red)
                ir_buffer.append(ir)
                if len(red_buffer) > 50:
                    red_buffer.pop(0)
                if len(ir_buffer) > 50:
                    ir_buffer.pop(0)

                heart_rate = calculate_heart_rate(ir_timestamps)
                spo2 = calculate_spo2(red_buffer, ir_buffer)

                oled.fill(0)
                oled.text("Pulse and O2", 0, 0)
                oled.text(f"Pulse: {heart_rate} bpm", 0, 20)
                if spo2 is not None:
                    oled.text(f"SpO2: {spo2}%", 0, 40)
                else:
                    oled.text("no data SpO2", 0, 40)
                oled.show()

                if HEART_RATE_LOW <= heart_rate <= HEART_RATE_HIGH:
                    buzzer.value(0)
                    green_led.value(1)
                    red_led.value(0)
                else:
                    green_led.value(0)
                    red_led.value(1)
                    buzzer.value(1)
                    sleep(0.2)
                    buzzer.value(0)
                    if not in_alert_state:
                        buzzer.value(1)
                        sleep(0.2)
                        buzzer.value(0)
                        in_alert_state = True
        sleep(0.1)
except KeyboardInterrupt:
    green_led.value(0)
    red_led.value(0)
    buzzer.value(0)
    oled.fill(0)
    oled.text("Program stopped", 0, 0)
    oled.show()

