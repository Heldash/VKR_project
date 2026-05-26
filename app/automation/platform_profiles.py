"""Platform-aware automation profiles."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformProfile:
    """Describes vendor-specific CLI rendering and collection defaults."""

    name: str
    template_name: str
    running_config_command: str
    interface_address_style: str = "mask"


_CISCO_LIKE = PlatformProfile(
    name="cisco_like",
    template_name="base_config_cisco_like.j2",
    running_config_command="show running-config",
)

_JUNIPER_JUNOS = PlatformProfile(
    name="juniper_junos",
    template_name="base_config_juniper_junos.j2",
    running_config_command="show configuration | display set",
    interface_address_style="cidr",
)

_HUAWEI_VRP = PlatformProfile(
    name="huawei_vrp",
    template_name="base_config_huawei_vrp.j2",
    running_config_command="display current-configuration",
)


_PLATFORM_ALIASES = {
    "cisco_ios": _CISCO_LIKE,
    "cisco_xe": _CISCO_LIKE,
    "cisco_xr": _CISCO_LIKE,
    "cisco_nxos": _CISCO_LIKE,
    "arista_eos": _CISCO_LIKE,
    "aruba_os": _CISCO_LIKE,
    "juniper_junos": _JUNIPER_JUNOS,
    "juniper": _JUNIPER_JUNOS,
    "huawei": _HUAWEI_VRP,
    "huawei_vrp": _HUAWEI_VRP,
}


def get_platform_profile(platform: str | None) -> PlatformProfile:
    """Returns the best matching CLI profile for the requested platform."""

    if platform is None:
        return _CISCO_LIKE
    return _PLATFORM_ALIASES.get(platform.strip().lower(), _CISCO_LIKE)
