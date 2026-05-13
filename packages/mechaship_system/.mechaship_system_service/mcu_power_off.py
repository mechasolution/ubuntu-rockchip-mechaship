from mcu_service import SerialHandler, Framer
import messages_pb2


def main():
    serial = SerialHandler()
    framer = Framer()

    msg = messages_pb2.ToMcuMessage()
    msg.power_off_evt.CopyFrom(messages_pb2.PowerOffEvt())
    frame = framer.encode(msg)
    serial.send(frame)


if __name__ == "__main__":
    main()
