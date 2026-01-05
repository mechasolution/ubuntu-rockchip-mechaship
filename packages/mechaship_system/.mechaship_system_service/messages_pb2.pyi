import nanopb_pb2 as _nanopb_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class NetworkType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NETWORK_TYPE_NONE: _ClassVar[NetworkType]
    NETWORK_TYPE_WLAN: _ClassVar[NetworkType]
    NETWORK_TYPE_LAN: _ClassVar[NetworkType]
NETWORK_TYPE_NONE: NetworkType
NETWORK_TYPE_WLAN: NetworkType
NETWORK_TYPE_LAN: NetworkType

class ToSbcMessage(_message.Message):
    __slots__ = ("battery_info", "power_off_req", "domain_id_info", "hw_info_res", "network_info_req", "ping_req")
    BATTERY_INFO_FIELD_NUMBER: _ClassVar[int]
    POWER_OFF_REQ_FIELD_NUMBER: _ClassVar[int]
    DOMAIN_ID_INFO_FIELD_NUMBER: _ClassVar[int]
    HW_INFO_RES_FIELD_NUMBER: _ClassVar[int]
    NETWORK_INFO_REQ_FIELD_NUMBER: _ClassVar[int]
    PING_REQ_FIELD_NUMBER: _ClassVar[int]
    battery_info: BatteryInfo
    power_off_req: PowerOffReq
    domain_id_info: DomainIdInfo
    hw_info_res: HwInfoRes
    network_info_req: NetworkInfoReq
    ping_req: PingReq
    def __init__(self, battery_info: _Optional[_Union[BatteryInfo, _Mapping]] = ..., power_off_req: _Optional[_Union[PowerOffReq, _Mapping]] = ..., domain_id_info: _Optional[_Union[DomainIdInfo, _Mapping]] = ..., hw_info_res: _Optional[_Union[HwInfoRes, _Mapping]] = ..., network_info_req: _Optional[_Union[NetworkInfoReq, _Mapping]] = ..., ping_req: _Optional[_Union[PingReq, _Mapping]] = ...) -> None: ...

class BatteryInfo(_message.Message):
    __slots__ = ("voltage", "percentage")
    VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    PERCENTAGE_FIELD_NUMBER: _ClassVar[int]
    voltage: float
    percentage: float
    def __init__(self, voltage: _Optional[float] = ..., percentage: _Optional[float] = ...) -> None: ...

class PowerOffReq(_message.Message):
    __slots__ = ("is_low_power",)
    IS_LOW_POWER_FIELD_NUMBER: _ClassVar[int]
    is_low_power: bool
    def __init__(self, is_low_power: bool = ...) -> None: ...

class DomainIdInfo(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class HwInfoRes(_message.Message):
    __slots__ = ("build_timestamp", "git_commit_hash")
    BUILD_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    GIT_COMMIT_HASH_FIELD_NUMBER: _ClassVar[int]
    build_timestamp: int
    git_commit_hash: str
    def __init__(self, build_timestamp: _Optional[int] = ..., git_commit_hash: _Optional[str] = ...) -> None: ...

class NetworkInfoReq(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class PingReq(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ToMcuMessage(_message.Message):
    __slots__ = ("ip_info", "hw_info_req", "power_off_evt", "network_info_res", "ping_res")
    IP_INFO_FIELD_NUMBER: _ClassVar[int]
    HW_INFO_REQ_FIELD_NUMBER: _ClassVar[int]
    POWER_OFF_EVT_FIELD_NUMBER: _ClassVar[int]
    NETWORK_INFO_RES_FIELD_NUMBER: _ClassVar[int]
    PING_RES_FIELD_NUMBER: _ClassVar[int]
    ip_info: IpInfo
    hw_info_req: HwInfoReq
    power_off_evt: PowerOffEvt
    network_info_res: NetworkInfoRes
    ping_res: PingRes
    def __init__(self, ip_info: _Optional[_Union[IpInfo, _Mapping]] = ..., hw_info_req: _Optional[_Union[HwInfoReq, _Mapping]] = ..., power_off_evt: _Optional[_Union[PowerOffEvt, _Mapping]] = ..., network_info_res: _Optional[_Union[NetworkInfoRes, _Mapping]] = ..., ping_res: _Optional[_Union[PingRes, _Mapping]] = ...) -> None: ...

class IpInfo(_message.Message):
    __slots__ = ("ipv4",)
    IPV4_FIELD_NUMBER: _ClassVar[int]
    ipv4: bytes
    def __init__(self, ipv4: _Optional[bytes] = ...) -> None: ...

class HwInfoReq(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class PowerOffEvt(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class NetworkInfoRes(_message.Message):
    __slots__ = ("type", "ssid", "rssi", "frequency")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SSID_FIELD_NUMBER: _ClassVar[int]
    RSSI_FIELD_NUMBER: _ClassVar[int]
    FREQUENCY_FIELD_NUMBER: _ClassVar[int]
    type: NetworkType
    ssid: str
    rssi: int
    frequency: int
    def __init__(self, type: _Optional[_Union[NetworkType, str]] = ..., ssid: _Optional[str] = ..., rssi: _Optional[int] = ..., frequency: _Optional[int] = ...) -> None: ...

class PingRes(_message.Message):
    __slots__ = ("ping_ms",)
    PING_MS_FIELD_NUMBER: _ClassVar[int]
    ping_ms: float
    def __init__(self, ping_ms: _Optional[float] = ...) -> None: ...
