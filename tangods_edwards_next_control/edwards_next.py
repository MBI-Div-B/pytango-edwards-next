from tango import DevState, DeviceProxy
from tango.server import Device, attribute, command, device_property, GreenMode
from edwardsserial.nEXT import nEXT
import time


class EdwardsNextControl(Device):
    ConnectType = device_property(
        dtype="str", default_value="serial", doc="either `net` or `serial`"
    )

    SerialPort = device_property(
        dtype="str",
        default_value="/dev/ttyUSB0",
        doc="Serial port of device",
    )

    Baudrate = device_property(
        dtype="int",
        default_value=9600,
        doc="Baudrate of serial port",
    )

    HostName = device_property(
        dtype="str",
        default_value="device.domain",
        doc="Hostname / IP address of device",
    )
    PortNumber = device_property(
        dtype="int",
        default_value=2001,
        doc="Socket port number of device",
    )
    Pressure_device_FQDN = device_property(
        dtype=str, doc="Tango device which indicates pressure in the evacuated volume"
    )
    frequency = attribute(
        label="frequency",
        dtype=float,
        unit="Hz",
        format="%2.2f",
    )
    motor_temperature = attribute(
        label="motor temp",
        dtype=float,
        unit="C",
        format="%2.2f",
    )
    controller_temperature = attribute(
        label="controller temp",
        dtype=float,
        unit="C",
        format="%2.2f",
    )
    current = attribute(
        label="current",
        dtype=float,
        unit="A",
        format="%2.2f",
    )
    voltage = attribute(
        label="voltage",
        dtype=float,
        unit="V",
        format="%2.2f",
    )
    power = attribute(
        label="power",
        dtype=float,
        unit="W",
        format="%2.2f",
    )

    def read_frequency(self):
        return self._frequency

    def read_motor_temperature(self):
        return self._motor_temp

    def read_controller_temperature(self):
        return self._controller_temp

    def read_current(self):
        return self._current

    def read_voltage(self):
        return self._voltage

    def read_power(self):
        return self._power

    def dev_state(self):
        state = DevState.UNKNOWN
        status_codes = self._state
        # STATUS_BITS = {
        # 0: "Fail status condition active",
        # 1: "Below stopped speed",
        # 2: "Above normal speed",
        # 3: "Vent valve energised",
        # 4: "Start command active",
        # 5: "Serial enable active",
        # 6: "Standby active",
        # 7: "Above 50% rotational speed",
        # 8: "Exclusive control mode selection",
        # 9: "Exclusive control mode selection",
        # 10: "Controller internal software mismatch",
        # 11: "Controller failed internal configuration",
        # 12: "Timer expired",
        # 13: "Overspeed or Overcurrent trip activated",
        # 14: "Thermistor error",
        # 15: "Serial enable become inactivate following a serial Start command",
        # }
        if 1 in status_codes:
            state = DevState.ON
        if 1 not in status_codes and 2 not in status_codes or 4 in status_codes:
            state = DevState.MOVING
        if 2 in status_codes or 7 in status_codes:
            state = DevState.RUNNING
        if any(x >= 10 for x in status_codes):
            state = DevState.ALARM
        return state

    def dev_status(self):
        return "\n".join(map(nEXT.STATUS_BITS.get, self._state))

    def always_executed_hook(self):
        now = time.time()
        if (now - self._last_query) > 0.3:
            # speed and state
            (
                self._frequency,
                state_bits,
            ) = self._control_interface.get_speed_and_state()
            self._state = list(
                filter(lambda ind: state_bits & (1 << ind), nEXT.STATUS_BITS.keys())
            )
            # voltage, current and powre
            (
                self._voltage,
                self._current,
                self._power,
            ) = self._control_interface.get_link()
            # temperatures
            (
                self._motor_temp,
                self._controller_temp,
            ) = self._control_interface.get_temps()
            self._last_query = now

    @command
    def turn_off(self):
        self._control_interface.stop()

    @command
    def turn_on(self):
        self._control_interface.start()

    def init_device(self):
        Device.init_device(self)
        self.get_device_properties()
        # since we are not able to set pump_on default value to False before
        # the ControlInterface will be created and auto_update is running instantly
        # we need to firstly disable auto_update
        self._control_interface = nEXT(
            com_port=self.SerialPort,
            socket_hostname=self.HostName,
            socket_port=self.PortNumber,
            connection_type=self.ConnectType,
        )
        self.init_dynamic_attributes()
        self._last_query = 0

    def init_dynamic_attributes(self):
        if self.Pressure_device_FQDN is not None:
            try:
                self.pressure_proxy = DeviceProxy(self.Pressure_device_FQDN)
                self.pressure_proxy.ping()
            except:
                self.info_stream(
                    f"Could not connect to pressure device {self.Pressure_device_FQDN}"
                )
            else:
                self.add_attribute(
                    attribute(
                        name="pressure",
                        label="pressure",
                        dtype=float,
                        format="%7.3e",
                        unit="mbar",
                        fget=self.get_pressure,
                    )
                )

    def get_pressure(self, attr_name):
        return self.pressure_proxy.pressure

    def delete_device(self):
        Device.delete_device(self)
        self._control_interface.close_connection()
