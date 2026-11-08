"""
A joystick drives two motors (Sketch 2) -- Raspberry Pi 4 version.

The Y axis sets forward and back. The X axis steers. Mixing the two gives
each motor its own speed:  left = y + x,  right = y - x.

This version runs entirely on the Raspberry Pi -- no Arduino needed. The Pi
drives the motor driver (L298N or similar) straight from its GPIO pins.

The Pi has no analog inputs, so the joystick is read through an MCP3008
analog-to-digital converter (ADC) over SPI. The MCP3008 is 10-bit, so its
readings run 0-1023, exactly like the Arduino's analogRead(). That means the
mixing math below is unchanged from the Arduino version.

One-time setup:
  1. Turn on SPI:  sudo raspi-config  >  Interface Options  >  SPI  >  Yes
                   then reboot.
  2. gpiozero comes with Raspberry Pi OS. If it's missing:
                   sudo apt install python3-gpiozero
  3. Run:          python3 two_motor_control_pi.py

Wiring (BCM GPIO numbers, physical header pin in [brackets]):

  MCP3008 (chip pin)        Raspberry Pi
    VDD  (16), VREF (15)  ->  3.3V            [1]
    AGND (14), DGND (9)   ->  GND             [6]
    CLK  (13)             ->  GPIO11 / SCLK   [23]
    DOUT (12)             ->  GPIO9  / MISO   [21]
    DIN  (11)             ->  GPIO10 / MOSI   [19]
    CS   (10)             ->  GPIO8  / CE0    [24]

  Joystick
    VCC (+5V)             ->  3.3V            [17]   <-- 3.3V, NOT 5V
    GND                   ->  GND             [9]
    VRx                   ->  MCP3008 CH0 (chip pin 1)
    VRy                   ->  MCP3008 CH1 (chip pin 2)

  Motor driver (L298N)
    IN1 -> GPIO17 [11]     IN2 -> GPIO27 [13]     ENA -> GPIO12 [32]
    IN3 -> GPIO22 [15]     IN4 -> GPIO23 [16]     ENB -> GPIO13 [33]
    GND -> any Pi GND (the Pi and the driver MUST share ground)
    Motor power (12V / VS) comes from a battery pack, never from the Pi.
    Remove the ENA and ENB jumpers on the L298N so the Pi controls speed.
"""

import time

# --- Pin Definitions (BCM GPIO numbers) ---
# Joystick (MCP3008 input channels)
VRX_CHANNEL = 0
VRY_CHANNEL = 1

# Motor A (Left)
IN1 = 17
IN2 = 27
ENA = 12

# Motor B (Right)
IN3 = 22
IN4 = 23
ENB = 13

# --- Constants ---
DEADZONE = 80        # Ignore tiny joystick noise
PWM_FREQUENCY = 500  # Hz, close to the Arduino's 490 Hz on pins 3 and 11
LOOP_DELAY = 0.01    # seconds between updates, same as delay(10)


def constrain(value, low, high):
    return max(low, min(high, value))


def mix(x_reading, y_reading):
    """Turn two 0-1023 joystick readings into (left_speed, right_speed).

    Each speed runs from -511 (full reverse) to 511 (full forward).
    """
    # Center the readings around 0
    x_val = x_reading - 511
    y_val = y_reading - 511

    # APPLY DEADZONE so small movements do nothing
    if abs(x_val) < DEADZONE:
        x_val = 0
    if abs(y_val) < DEADZONE:
        y_val = 0

    # Stronger steering: amplify X by 1.2 (steering priority).
    # Written as 12/10 so whole numbers stay exact; int() drops the
    # fraction the same way the Arduino's int does.
    x_val = int(x_val * 12 / 10)

    # Mix joystick values for differential steering
    left_speed = constrain(y_val + x_val, -511, 511)
    right_speed = constrain(y_val - x_val, -511, 511)
    return left_speed, right_speed


def motor_signals(speed):
    """Turn one motor's speed (-511 to 511) into (in_a, in_b, pwm).

    in_a and in_b are the two direction pins (1 = HIGH, 0 = LOW).
    pwm is 0-255 for the enable pin.
    """
    if speed > 0:
        in_a, in_b = 1, 0          # forward
    elif speed < 0:
        in_a, in_b = 0, 1          # reverse
    else:
        in_a, in_b = 0, 0          # stopped

    # Map from -511/511 range to 0-255 PWM range
    return in_a, in_b, abs(speed) // 2


def connect():
    """Set up the joystick ADC and the motor pins.

    Returns (read_joystick, drive, close):
      read_joystick() -> (x_reading, y_reading), each 0-1023
      drive(left_speed, right_speed) sends direction and PWM to both motors
      close() releases all the GPIO pins
    """
    # Imported here (not at the top) so the trackpad tester can use mix()
    # and motor_signals() on a laptop that doesn't have gpiozero.
    from gpiozero import MCP3008, DigitalOutputDevice, PWMOutputDevice

    # setup(): same roles as pinMode in the sketch
    joy_x = MCP3008(channel=VRX_CHANNEL)
    joy_y = MCP3008(channel=VRY_CHANNEL)

    left = (DigitalOutputDevice(IN1), DigitalOutputDevice(IN2),
            PWMOutputDevice(ENA, frequency=PWM_FREQUENCY))
    right = (DigitalOutputDevice(IN3), DigitalOutputDevice(IN4),
             PWMOutputDevice(ENB, frequency=PWM_FREQUENCY))

    def read_joystick():
        # gpiozero gives 0.0-1.0; scale back to 0-1023 like analogRead()
        return round(joy_x.value * 1023), round(joy_y.value * 1023)

    def drive(left_speed, right_speed):
        for speed, (pin_a, pin_b, enable) in ((left_speed, left),
                                              (right_speed, right)):
            in_a, in_b, pwm = motor_signals(speed)
            pin_a.value = in_a
            pin_b.value = in_b
            enable.value = pwm / 255   # gpiozero PWM takes 0.0-1.0

    def close():
        for device in (joy_x, joy_y, *left, *right):
            device.close()

    return read_joystick, drive, close


def main():
    read_joystick, drive, close = connect()

    try:
        # loop()
        while True:
            x_reading, y_reading = read_joystick()
            drive(*mix(x_reading, y_reading))
            time.sleep(LOOP_DELAY)

    except KeyboardInterrupt:
        pass
    finally:
        # Always stop both motors when the script ends
        drive(0, 0)
        close()


if __name__ == "__main__":
    main()
