.. zephyr:code-sample:: bme280
   :name: BME280 humidity and pressure sensor
   :relevant-api: sensor_interface

   Get temperature, pressure, and humidity data from a BME280 sensor.

Overview
********

This sample shows how to use the Zephyr :ref:`sensor` API driver for the
`Bosch BME280`_ environmental sensor.

.. _Bosch BME280:
   https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/

The sample periodically reads temperature, pressure and humidity data from the
first available BME280 device discovered in the system. The sample checks the
sensor in polling mode (without interrupt trigger).
