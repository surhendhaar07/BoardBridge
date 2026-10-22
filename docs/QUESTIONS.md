# 10 real questions my user will ask

Write them the way your user would type them. At least 3 must need more than one page to answer, and at least 1 must be a question your documents cannot answer.

| # | Question | Where the answer is (document, page) | Needs more than one page? |
|---|---|---|---|
| 1 | I want to connect a BME280 sensor to my board using I2C. Which driver should I use, what compatible string and devicetree properties do I need, and how do I configure it? | `samples/sensor/bme280/README.rst`, `dts/bindings/sensor/bosch,bme280.yaml`, `drivers/sensor/bosch/bme280/` | Yes |
| 2 | I'm using the nRF52840 DK and want to generate a PWM signal. Is there a working example, and how do I configure the pins, period, and pulse width? | `samples/drivers/pwm/`, `boards/nordic/nrf52840dk/`, `dts/bindings/pwm/` | Yes |
| 3 | I'm porting Zephyr to a custom ARM Cortex-M board. Which files do I need to create or modify for the board definition, devicetree, Kconfig, and build configuration? | `doc/hardware/porting/board_porting.rst`, `boards/` | Yes |
| 4 | I enabled the CAN controller on my STM32 board, but my application still can't use it. How do I check the devicetree settings, required Kconfig options, driver support, and CAN sample code? | `drivers/can/`, `samples/drivers/can/`, relevant STM32 board devicetree files | Yes |
| 5 | My BME280 device returns not ready during startup. How can I trace the initialization process and figure out whether the problem is with the driver, devicetree configuration, or I2C/SPI bus? | `samples/sensor/bme280/`, `drivers/sensor/bosch/bme280/`, relevant devicetree binding | Yes |
| 6 | How do I enable UART console output and `printk()` on my board? Which Kconfig options and devicetree settings should I check? | `drivers/console/`, `subsys/console/`, relevant board devicetree files | Yes |
| 7 | Can you show me a working example of a GPIO button interrupt and explain how to configure the callback and detect button presses? | `samples/basic/button/README.rst`, `samples/basic/button/src/main.c`, `include/zephyr/drivers/gpio.h` | No |
| 8 | I want to connect a sensor over SPI instead of I2C. How do I find out whether the driver supports SPI and configure the SPI controller, chip select, and devicetree overlay? | `samples/sensor/bme280/`, `dts/bindings/spi/`, `drivers/sensor/bosch/bme280/` | Yes |
| 9 | I'm new to Zephyr. How do I build and flash the Blinky sample for my development board, and what should I check if the LED doesn't blink? | `samples/basic/blinky/README.rst`, `samples/basic/blinky/src/main.c`, relevant board devicetree files | No |
| 10 | Can you guarantee that my custom PCB will communicate reliably with a BME280 over SPI at 8 MHz under my actual wiring, temperature, and electrical-noise conditions? | None — cannot be answered from repository documents alone; physical hardware testing is required. | No |
