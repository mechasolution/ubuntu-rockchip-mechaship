from mcu_service import McuService


def main():
    mcu_service = McuService()
    ser = mcu_service.connect_serial()

    ser.write(f"$PO\r\n".encode())


if __name__ == "__main__":
    main()
