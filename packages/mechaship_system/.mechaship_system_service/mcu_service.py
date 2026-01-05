import os
import re
import socket
import stat
import struct
import subprocess
import time
import zlib
from collections import deque
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import ping3
import serial
from cobs import cobs

import messages_pb2


class Framer:
    def __init__(self):
        pass

    def decode(self, arr: bytes) -> messages_pb2.ToSbcMessage:
        # COBS
        cobs_decoded = cobs.decode(arr)
        if len(cobs_decoded) < 4:
            raise ValueError(f"decoded too short: {len(cobs_decoded)} bytes")

        # CRC32
        payload = cobs_decoded[:-4]
        (crc_recv,) = struct.unpack("<I", cobs_decoded[-4:])
        crc_calc = zlib.crc32(payload) & 0xFFFFFFFF
        if crc_calc != crc_recv:
            raise ValueError(
                f"CRC mismatch: calc=0x{crc_calc:08X}, recv=0x{crc_recv:08X}"
            )

        # protobuf
        msg = messages_pb2.ToSbcMessage()
        msg.ParseFromString(payload)

        return msg

    def encode(self, data: messages_pb2.ToMcuMessage):
        payload = data.SerializeToString()
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        frame = payload + struct.pack("<I", crc)
        return cobs.encode(frame)


class SerialHandler:
    def __init__(self):
        self.buf = deque(maxlen=1024)
        self.ser = None  # 초기값을 None으로 설정

        self.connect()

    def connection_status(self) -> bool:
        return self.ser.is_open

    def connect(
        self, port="/dev/ttyMCU", baudrate=115200, timeout=0.1, write_timeout=1
    ):
        if self.ser is not None and self.ser.is_open:
            try:
                self.ser.close()
            except Exception as e:
                pass

        while True:
            try:
                self.ser = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=timeout,
                    write_timeout=write_timeout,
                )
                if self.ser.is_open:
                    break

            except serial.SerialException as e:
                time.sleep(1)

    def fetch(self) -> tuple[bool, bool]:
        while True:
            try:
                frame = self.ser.read_until(b"\0")
                if not frame:
                    return False, False

                self.buf.extend(frame)
                if frame.endswith(b"\0"):
                    return True, self.ser.readable()

            except serial.SerialException as e:
                self.connect()

    def get_frame(self) -> bytes:
        arr = bytearray()

        while self.buf:
            c = self.buf.popleft()
            if c == 0:
                return bytes(arr)
            arr.append(c)

        return b""

    def send(self, msg: bytes):
        while True:
            try:
                self.ser.write(msg)
                self.ser.write(b"\0")
                return

            except serial.SerialException as e:
                self.connect()


class Dispatcher:
    SOCK_PATH = "/tmp/mechaship_service.sock"
    IP_ADDR_FAIL = [0, 0, 0, 0]

    def __init__(self):
        self.last_battery_check_time: Optional[int] = 0
        self.last_battery_percentage: Optional[int] = 100
        self.battery_voltage: Optional[float] = None
        self.battery_percentage: Optional[float] = None
        self.domain_id_mcu: Optional[int] = None
        self.domain_id_sbc: Optional[int] = None
        self.build_timestamp_utc_s: Optional[int] = None
        self.build_timestamp_kst: Optional[datetime] = None
        self.build_hash: Optional[str] = None

        self.network_connection_method: Optional[str] = None  # LAN / WLAN / NONE
        self.network_interface_name: Optional[str] = None
        self.network_ip_addr: Optional[str] = None
        self.network_ip_addr_router: Optional[str] = None
        self.network_ssid: Optional[str] = None
        self.network_rssi: Optional[int] = None
        self.network_frequency: Optional[int] = None
        self.network_ping: Optional[float] = None

        if os.path.exists(self.SOCK_PATH):
            os.remove(self.SOCK_PATH)
        self.battery_sock_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.battery_sock_server.bind(self.SOCK_PATH)
        self.battery_sock_server.listen(1)
        self.battery_sock_server.settimeout(0.1)
        os.chmod(self.SOCK_PATH, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

    def socket_worker(self):
        try:
            conn, _ = self.battery_sock_server.accept()
            data = conn.recv(1024).decode()
            if data.strip() == "get_battery":
                conn.send(
                    f"Battery: {self.battery_voltage:.1f} V / {self.battery_percentage:.0f} %\n".encode()
                )
            elif data.strip() == "get_mcu_info":
                if self.build_timestamp_kst is None:
                    conn.send(
                        f"FW Version: Loading..\nFW Hash: Loading..\nROS_DOMAIN_ID(SBC): Loading..\nROS_DOMAIN_ID(MCU): Loading..\n".encode()
                    )
                else:
                    conn.send(
                        f"FW Version: {self.build_timestamp_kst.strftime("%Y-%m-%d %H:%M:%S %Z%z")}\nFW Hash: {self.build_hash}\nROS_DOMAIN_ID(SBC): {self.domain_id_sbc}\nROS_DOMAIN_ID(MCU): {self.domain_id_mcu}\n".encode()
                    )
            elif data.strip() == "get_mcu_ros_domain_id":
                conn.send(f"{self.domain_id_mcu}".encode())
            conn.close()

        except socket.timeout:
            pass
        except BrokenPipeError:
            pass

    def update_interface_info(self):
        try:
            result = subprocess.run(
                ["ip", "route"], capture_output=True, text=True, check=True
            )
            output = result.stdout

            match = re.search(
                r"^default\s+via\s+(\S+)\s+dev\s+(\S+).*?\bsrc\s+(\d+\.\d+\.\d+\.\d+)",
                output,
                re.MULTILINE,
            )
            if match:
                self.network_ip_addr_router = list(map(int, match.group(1).split(".")))
                self.network_interface_name = match.group(2)
                self.network_ip_addr = list(map(int, match.group(3).split(".")))
            else:
                self.network_connection_method = "NONE"
                self.network_interface_name = ""
                self.network_ip_addr = self.IP_ADDR_FAIL
                self.network_ip_addr_router = self.IP_ADDR_FAIL
                self.network_ssid = ""
                self.network_rssi = 0
                self.network_frequency = 0
                return

        except subprocess.CalledProcessError:
            self.network_connection_method = "NONE"
            self.network_interface_name = ""
            self.network_ip_addr = self.IP_ADDR_FAIL
            self.network_ip_addr_router = self.IP_ADDR_FAIL
            self.network_ssid = ""
            self.network_rssi = 0
            self.network_frequency = 0

        # Wi-Fi인지 유선인지 확인
        if os.path.isdir(f"/sys/class/net/{self.network_interface_name}/wireless"):
            self.network_connection_method = "WLAN"
        else:
            self.network_connection_method = "LAN"
            self.network_ssid = "**LAN**"
            self.network_rssi = 0
            self.network_frequency = 0
            return

        # 네트워크 정보 파싱
        try:
            result = subprocess.run(
                ["iw", "dev", self.network_interface_name, "link"],
                capture_output=True,
                text=True,
                check=True,
            )
            output = result.stdout
            # SSID
            ssid_match = re.search(r"SSID:\s(.+)", output)
            if ssid_match:
                self.network_ssid = ssid_match.group(1).strip()
            else:
                self.network_ssid = ""

            # RSSI dBm (signal)
            signal_match = re.search(r"signal:\s(-?\d+)", output)
            if signal_match:
                self.network_rssi = int(signal_match.group(1))
                # quality = 2 * (int(signal_match.group(1)) + 100)
                # self.network_rssi = max(0, min(100, quality))
            else:
                self.network_rssi = 0

            # frequency -> channel
            freq_match = re.search(r"freq:\s(\d+)", output)
            if freq_match:
                self.network_frequency = int(freq_match.group(1))
            else:
                self.network_frequency = 0

        except subprocess.CalledProcessError:
            self.network_ssid = ""
            self.network_rssi = 0
            self.network_frequency = 0
            return

        return

    def get_ping_ms(self) -> float:
        if self.network_ip_addr_router == self.IP_ADDR_FAIL:
            return -1.0
        ping_ms = ping3.ping(
            f"{self.network_ip_addr_router[0]}.{self.network_ip_addr_router[1]}.{self.network_ip_addr_router[2]}.{self.network_ip_addr_router[3]}",
            timeout=0.4,
            unit="ms",
        )
        if ping_ms is None:
            ping_ms = -1.0

        return ping_ms

    def get_ip_addr(self) -> list:
        return self.network_ip_addr

    def process_rx(
        self, msg: messages_pb2.ToSbcMessage
    ) -> tuple[bool, messages_pb2.ToMcuMessage]:
        which = msg.WhichOneof("data")

        if which == "battery_info":
            bi = msg.battery_info
            self.battery_voltage = bi.voltage
            self.battery_percentage = bi.percentage

            current_time = time.time()
            if (
                current_time - self.last_battery_check_time >= 300
                and self.battery_percentage < self.last_battery_percentage
            ):  # 5분마다 검사, 배터리 잔량이 늘어나고 있는 경우 무시
                if self.battery_percentage < 10:
                    self.last_battery_check_time = current_time
                    message = (
                        f"⚠️ [배터리 잔량 경고]\n"
                        f"현재 배터리 잔량이 매우 낮습니다. ({self.battery_percentage:.1f}%)\n"
                        f"시스템을 안전하게 종료한 후 배터리를 충전해주세요.\n"
                    )

                    subprocess.run(["wall", message])

            self.last_battery_percentage = self.battery_percentage

            return False, None

        elif which == "power_off_req":
            po = msg.power_off_req

            message = f"⚠️ [시스템 종료]\n5초 뒤 시스템이 종료됩니다.\n"
            subprocess.run(["wall", message])

            time.sleep(5)

            os.system("/usr/sbin/poweroff")

            return False, None

        elif which == "domain_id_info":
            di = msg.domain_id_info
            self.domain_id_mcu = di.id

            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    "source /home/ubuntu/ros2_ws/install/setup.bash && echo $ROS_DOMAIN_ID",
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            self.domain_id_sbc = int(result.stdout.strip())

            return False, None

        elif which == "hw_info_res":
            hw = msg.hw_info_res
            self.build_timestamp_utc_s = hw.build_timestamp
            self.build_hash = hw.git_commit_hash
            self.build_timestamp_kst = datetime.fromtimestamp(
                self.build_timestamp_utc_s, tz=timezone.utc
            ).astimezone(ZoneInfo("Asia/Seoul"))

            return False, None

        elif which == "network_info_req":
            self.update_interface_info()
            msg_to_mcu = messages_pb2.ToMcuMessage()
            if self.network_connection_method == "NONE":
                msg_to_mcu.network_info_res.type = messages_pb2.NETWORK_TYPE_NONE
            elif self.network_connection_method == "WLAN":
                msg_to_mcu.network_info_res.type = messages_pb2.NETWORK_TYPE_WLAN
            elif self.network_connection_method == "LAN":
                msg_to_mcu.network_info_res.type = messages_pb2.NETWORK_TYPE_LAN
            msg_to_mcu.network_info_res.ssid = self.network_ssid
            msg_to_mcu.network_info_res.rssi = self.network_rssi
            msg_to_mcu.network_info_res.frequency = self.network_frequency

            return True, msg_to_mcu

        elif which == "ping_req":
            msg_to_mcu = messages_pb2.ToMcuMessage()
            msg_to_mcu.ping_res.ping_ms = self.get_ping_ms()

            return True, msg_to_mcu

        else:
            pass


def main():
    serialhd = SerialHandler()
    framer = Framer()
    dispatcher = Dispatcher()

    last_ip_send_time = 0
    last_serial_connection = False

    while True:
        current_time = time.time()

        while True:
            (is_frame, is_left) = serialhd.fetch()
            if is_left is False:
                break
            if is_frame is True:
                msg = framer.decode(serialhd.get_frame())
                (is_res, msg) = dispatcher.process_rx(msg)
                if is_res is True:
                    frame = framer.encode(msg)
                    serialhd.send(frame)

        current_connection = serialhd.connection_status()
        if current_connection is not last_serial_connection:
            last_serial_connection = current_connection
            if current_connection is True:
                msg_to_mcu = messages_pb2.ToMcuMessage()
                msg_to_mcu.hw_info_req.CopyFrom(messages_pb2.HwInfoReq())
                frame = framer.encode(msg_to_mcu)
                serialhd.send(frame)

        if current_time - last_ip_send_time >= 5:
            last_ip_send_time = current_time

            dispatcher.update_interface_info()
            msg_to_mcu = messages_pb2.ToMcuMessage()
            msg_to_mcu.ip_info.ipv4 = struct.pack("!4B", *dispatcher.network_ip_addr)
            encoded = framer.encode(msg_to_mcu)
            serialhd.send(encoded)

        dispatcher.socket_worker()


if __name__ == "__main__":
    main()
