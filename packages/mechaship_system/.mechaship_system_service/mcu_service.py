import os
import re
import socket
import stat
import subprocess
import time
from datetime import datetime
from typing import NamedTuple

import ping3
import psutil
import serial


class InterfaceInfo(NamedTuple):
    connect_method: str
    ssid: str
    rssi: int
    frequency: int


class McuService:
    SOCK_PATH = "/tmp/mechaship_service.sock"
    IP_ADDR_FAIL = [0, 0, 0, 0]

    def __init__(self):
        self.last_check_time = 0
        self.last_percentage = 100
        self.battery_voltage = -1.0
        self.battery_percentage = -1.0
        self.build_date = "Unknown"
        self.build_hash = "Unknown"
        self.domain_id_mcu = -1
        self.domain_id_sbc = -1
        self.domain_id_warn = False

        if os.path.exists(self.SOCK_PATH):
            os.remove(self.SOCK_PATH)

        self.battery_sock_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.battery_sock_server.bind(self.SOCK_PATH)
        self.battery_sock_server.listen(1)
        self.battery_sock_server.settimeout(0.1)

        os.chmod(self.SOCK_PATH, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        self.network_connection_method = "NONE"  # LAN/WLAN/NONE
        self.network_interface_name = ""  # wlP4p65s0 등
        self.network_ip_addr = self.IP_ADDR_FAIL
        self.network_ip_addr_router = self.IP_ADDR_FAIL
        self.network_ssid = "**Unknown**"
        self.network_rssi = 0
        self.network_frequency = 0
        self.network_ping = 0.0

        self.is_req_iw = False
        self.is_req_ping = False

    def update_network_info(self):
        # 인터페이스, IP
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
                self.network_ssid = "**Unknown**"
                self.network_rssi = 0
                self.network_frequency = 0
                return

        except subprocess.CalledProcessError:
            self.network_connection_method = "NONE"
            self.network_interface_name = ""
            self.network_ip_addr = self.IP_ADDR_FAIL
            self.network_ip_addr_router = self.IP_ADDR_FAIL
            self.network_ssid = "**Unknown**"
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
                self.network_ssid = "**Unknown**"

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
            self.network_ssid = "**Unknown**"
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

    def __freq_to_channel(self, freq):
        # 2.4GHz
        if 2412 <= freq <= 2472:
            return (freq - 2407) // 5
        if freq == 2484:
            return 14

        # 5GHz
        if 5000 <= freq <= 5900:
            return (freq - 5000) // 5

        # 6GHz (Wi-Fi 6E)
        if 5925 <= freq <= 7125:
            return (freq - 5950) // 5 + 1

        return 0

    def get_interface_info(self) -> InterfaceInfo:
        return InterfaceInfo(
            self.network_connection_method,
            self.network_ssid,
            self.network_rssi,
            self.network_frequency,
        )

    def get_ip_addr(self) -> list:
        return self.network_ip_addr

    def connect_serial(
        self, port="/dev/ttyMCU", baudrate=115200, timeout=1, write_timeout=1
    ) -> serial.Serial:
        while True:
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=timeout,
                    write_timeout=write_timeout,
                )
                ip_message = f"$IN\r\n"
                ser.write(ip_message.encode())

                # reinit variables
                self.battery_voltage = -1.0
                self.battery_percentage = -1.0
                self.build_date = "Unknown"
                self.build_hash = "Unknown"
                self.domain_id_mcu = -1
                self.domain_id_sbc = -1
                self.domain_id_warn = False

                return ser
            except serial.SerialException as e:
                time.sleep(1)

    def parse_rx(self, data: str) -> None:
        sp = data.split(",")

        if sp[0] == "$BT":  # 배터리 잔량
            current_time = time.time()
            voltage = float(sp[1])
            percentage = float(sp[2])
            self.battery_voltage = voltage
            self.battery_percentage = percentage

            if (
                current_time - self.last_check_time >= 300
                and percentage < self.last_percentage
            ):  # 5분마다 검사, 배터리 잔량이 늘어나고 있는 경우 무시
                if percentage < 10:
                    self.last_check_time = current_time
                    message = (
                        f"⚠️ [배터리 잔량 경고]\n"
                        f"현재 배터리 잔량이 매우 낮습니다. ({percentage:.1f}%)\n"
                        f"시스템을 안전하게 종료한 후 배터리를 충전해주세요.\n"
                    )

                    subprocess.run(["wall", message])

            self.last_percentage = percentage

        elif sp[0] == "$PO":  # 전원 종료
            message = f"⚠️ [시스템 종료]\n5초 뒤 시스템이 종료됩니다.\n"
            subprocess.run(["wall", message])

            time.sleep(5)

            os.system("/usr/sbin/poweroff")

        elif sp[0] == "$IN":  # 펌웨어 정보
            datetime_str = f"{sp[1]} {sp[2]}"
            self.build_date = datetime.strptime(datetime_str, "%b %d %Y %H:%M:%S")
            self.build_hash = sp[3]

        elif sp[0] == "$ID":  # DOMAIN ID
            self.domain_id_mcu = int(sp[1])

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

        elif sp[0] == "$IW":  # 네트워크 정보 요청
            self.is_req_iw = True

        elif sp[0] == "$PG":  # Ping
            self.is_req_ping = True


def main():
    mcu_service = McuService()
    ser = mcu_service.connect_serial()

    last_ip_send_time = 0
    last_network_detailed_send_time = 0

    try:
        while True:
            current_time = time.time()

            try:
                # IP 보고
                if current_time - last_ip_send_time >= 5:
                    mcu_service.update_network_info()
                    ip_parts = mcu_service.get_ip_addr()
                    ip_message = f"$IP,{ip_parts[0]},{ip_parts[1]},{ip_parts[2]},{ip_parts[3]}\r\n"
                    ser.write(ip_message.encode())
                    last_ip_send_time = current_time

                # 인터페이스 정보 전달
                if mcu_service.is_req_iw:
                    mcu_service.is_req_iw = False
                    mcu_service.update_network_info()
                    info = mcu_service.get_interface_info()

                    message = f"$IW,{info.connect_method},{info.ssid},{info.rssi},{info.frequency}\r\n"
                    ser.write(message.encode())

                # ping 전달 (라우터로 ping)
                if mcu_service.is_req_ping:
                    mcu_service.is_req_ping = False
                    mcu_service.update_network_info()
                    ping_ms = mcu_service.get_ping_ms()

                    message = f"$PG,{ping_ms:.2f}\r\n"
                    ser.write(message.encode())

                # RX
                if ser.in_waiting > 0:
                    r = ser.readline().strip().decode()
                    mcu_service.parse_rx(r)

            except (serial.SerialException, OSError) as e:
                ser.close()
                ser = mcu_service.connect_serial()
                last_ip_send_time = time.time() - 4  # 재연결 후 1초 뒤 전송

            try:
                conn, _ = mcu_service.battery_sock_server.accept()
                data = conn.recv(1024).decode()
                if data.strip() == "get_battery":
                    conn.send(
                        f"Battery: {mcu_service.battery_voltage:.1f} V / {mcu_service.battery_percentage:.0f} %\n".encode()
                    )
                elif data.strip() == "get_mcu_info":
                    conn.send(
                        f"FW Version: {mcu_service.build_date}\nFW Hash: {mcu_service.build_hash}\nROS_DOMAIN_ID(SBC): {mcu_service.domain_id_sbc}\nROS_DOMAIN_ID(MCU): {mcu_service.domain_id_mcu}\n".encode()
                    )
                elif data.strip() == "get_mcu_ros_domain_id":
                    conn.send(f"{mcu_service.domain_id_mcu}".encode())
                conn.close()

            except socket.timeout:
                pass
            except BrokenPipeError:
                pass

            else:
                time.sleep(0.1)

    except KeyboardInterrupt:
        pass

    finally:
        if ser and ser.is_open:
            ser.close()


if __name__ == "__main__":
    main()
