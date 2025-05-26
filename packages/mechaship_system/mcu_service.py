import os
import subprocess
import re
import psutil
import time
import serial


def __find_ip_interface() -> str:
    try:
        result = subprocess.run(
            ["ip", "route"], capture_output=True, text=True, check=True
        )
        output = result.stdout

        match = re.search(r"^default .* dev (\S+)", output, re.MULTILINE)
        if match:
            return match.group(1)
        else:
            return ""
    except subprocess.CalledProcessError as e:
        print(f"Error getting default interface: {e}")
        return ""


def __get_ip_addr() -> list:
    interface = __find_ip_interface()
    if not interface:  # default interface 없음
        return [0, 0, 0, 0]

    addrs = psutil.net_if_addrs()
    if interface not in addrs:  # default interface에 ip 부여 안됨
        return [0, 0, 0, 0]

    for addr in addrs[interface]:
        if addr.family.name == "AF_INET":  # IPv4
            ip_parts = list(map(int, addr.address.split(".")))
            return ip_parts

        # IP 주소 찾지 못함
        return [0, 0, 0, 0]

    return [0, 0, 0, 0]


def __connect_serial(
    port="/dev/ttyMCU", baudrate=115200, timeout=1, write_timeout=1
) -> serial.Serial:
    while True:
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                write_timeout=write_timeout,
            )
            return ser
        except serial.SerialException as e:
            time.sleep(1)


last_check_time = 0
last_percentage = 100
last_20_alert = False


def __parse_rx(data: str):
    sp = data.split(",")

    if sp[0] == "$BT":  # 배터리 잔량
        global last_check_time
        global last_percentage
        global last_20_alert
        current_time = time.time()
        percentage = float(sp[2])

        if (
            current_time - last_check_time >= 300 and percentage < last_percentage
        ):  # 5분마다 검사, 배터리 잔량이 늘어나고 있는 경우 무시
            if percentage < 10:
                last_check_time = current_time
                message = (
                    f"⚠️ [배터리 잔량 경고]\n"
                    f"현재 배터리 잔량이 매우 낮습니다. ({percentage:.1f}%)\n"
                    f"시스템을 안전하게 종료한 후 배터리를 충전해주세요.\n"
                )

                subprocess.run(["wall", message])

        last_percentage = percentage

    elif sp[0] == "$PO":  # 전원 종료
        message = f"⚠️ [시스템 종료]\n5초 뒤 시스템이 종료됩니다.\n"
        subprocess.run(["wall", message])

        time.sleep(5)

        os.system("/usr/sbin/poweroff")


def main():
    ser = __connect_serial()
    last_ip_send_time = 0

    try:
        while True:
            current_time = time.time()

            # IP 보고
            if current_time - last_ip_send_time >= 5:
                try:
                    ip_parts = __get_ip_addr()
                    ip_message = f"$IP,{ip_parts[0]},{ip_parts[1]},{ip_parts[2]},{ip_parts[3]}\r\n"
                    ser.write(ip_message.encode())
                    last_ip_send_time = current_time
                except (serial.SerialException, OSError) as e:
                    ser.close()
                    ser = __connect_serial()
                    last_ip_send_time = time.time() - 4  # 재연결 후 1초 뒤 전송

            # RX
            try:
                if ser.in_waiting > 0:
                    r = ser.readline().strip().decode()
                    __parse_rx(r)

            except (serial.SerialException, OSError) as e:
                ser.close()
                ser = __connect_serial()
                last_ip_send_time = time.time() - 4  # 재연결 후 1초 뒤 전송

            time.sleep(0.1)

    except KeyboardInterrupt:
        pass
    finally:
        if ser and ser.is_open:
            ser.close()


main()
