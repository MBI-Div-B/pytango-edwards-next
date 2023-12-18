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
        # 6: "Serial enable active",
        # 7: "Above 50%\ rotational speed",
        # 8: "Exclusive control mode selection",
        # 9: "Exclusive control mode selection",
        # 10: "Controller internal software mismatch",
        # 11: "Controller failed internal configuration",
        # 12: "Timer expired",
        # 13: "Overspeed or Overcurrent trip activated",
        # 14: "Thermistor error",
        # 15: "Serial enable become inactivate following a serial Start command",
        # }
        if 0 in status_codes:
            state = DevState.INIT
        if 4 in status_codes or 5 in status_codes:
            state = DevState.MOVING
        if 2 in status_codes:
            state = DevState.RUNNING
        if 11 in status_codes:
            state = DevState.ON
        if 14 in status_codes or 13 in status_codes or 14 in status_codes:
            state = DevState.ALARM
        if 0 in status_codes:
            state = DevState.FAULT
        return state

    def dev_status(self):
        status_codes = self._state
        return "\n".join(map(self.STATUS_BITS.get, status_codes))

    def read_attr_hardware(self, attr_list):
        attr_names = [
            self.get_device_attr().get_attr_by_ind(attr_id).get_name()
            for attr_id in attr_list
        ]
        now = time.time()
        if "frequency" in attr_names or "State" in attr_names or "Status" in attr_names:
            if (now - self._last_state_query) > 0.2:
                (
                    self._frequency,
                    self._state,
                ) = self._control_interface.get_speed_and_state()
                self._last_state_query = now
        if "current" in attr_names or "votage" in attr_names or "power" in attr_names:
            if (now - self._last_link_query) > 0.2:
                (
                    self._voltage,
                    self._current,
                    self._power,
                ) = self._control_interface.get_link()
                self._last_link_query = now
        if "controller_temperature" in attr_names or "motor_temperature" in attr_names:
            if (now - self._last_temp_query) > 0.2:
                (
                    self._motor_temp,
                    self._controller_temp,
                ) = self._control_interface.get_temps()
                self._last_temp_query = now

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
        self._last_state_query = (
            self._last_link_query
        ) = self._last_temp_query = time.time()

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
