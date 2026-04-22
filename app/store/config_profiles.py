"""In-memory catalog of reusable configuration profiles."""

from app.automation.models import (
    BaseConfigurationOverrides,
    BaseConfigurationProfile,
    BaseConfigurationRequest,
)
from app.domain.exceptions import DeviceNotFoundError
from app.domain.models import InterfaceSpec


DEFAULT_CONFIG_PROFILES: tuple[BaseConfigurationProfile, ...] = (
    BaseConfigurationProfile(
        name="branch-edge",
        description="Baseline for branch edge routers with WAN uplink and loopback.",
        domain_name="branch.lab",
        banner_motd="Authorized branch edge device",
        ntp_server="192.0.2.200",
        interfaces=[
            InterfaceSpec(
                name="Loopback0",
                description="Management loopback",
                ipv4_address="10.255.0.1/32",
            ),
            InterfaceSpec(
                name="GigabitEthernet0/0",
                description="WAN uplink",
                enabled=True,
            ),
        ],
    ),
    BaseConfigurationProfile(
        name="campus-distribution",
        description="Baseline for campus distribution routers with user gateway uplink.",
        domain_name="campus.lab",
        banner_motd="Managed campus distribution router",
        ntp_server="192.0.2.210",
        interfaces=[
            InterfaceSpec(
                name="Loopback0",
                description="Routing loopback",
                ipv4_address="10.255.1.1/32",
            ),
            InterfaceSpec(
                name="GigabitEthernet0/1",
                description="User VLAN gateway",
                enabled=True,
            ),
        ],
    ),
)


class ConfigurationProfileRepository:
    """Stores reusable configuration profiles in memory."""

    def __init__(
        self,
        profiles: tuple[BaseConfigurationProfile, ...] = DEFAULT_CONFIG_PROFILES,
    ) -> None:
        self._profiles = {profile.name: profile for profile in profiles}

    def list_profiles(self) -> list[BaseConfigurationProfile]:
        return list(self._profiles.values())

    def get_profile(self, profile_name: str) -> BaseConfigurationProfile:
        profile = self._profiles.get(profile_name)
        if profile is None:
            raise DeviceNotFoundError(f"Configuration profile '{profile_name}' not found")
        return profile

    def build_request(
        self,
        profile_name: str,
        overrides: BaseConfigurationOverrides,
    ) -> BaseConfigurationRequest:
        profile = self.get_profile(profile_name)
        merged_interfaces = [interface.model_copy(deep=True) for interface in profile.interfaces]
        positions = {interface.name: index for index, interface in enumerate(merged_interfaces)}

        for interface in overrides.interfaces:
            interface_copy = interface.model_copy(deep=True)
            if interface.name in positions:
                merged_interfaces[positions[interface.name]] = interface_copy
            else:
                positions[interface.name] = len(merged_interfaces)
                merged_interfaces.append(interface_copy)

        return BaseConfigurationRequest(
            hostname=overrides.hostname,
            domain_name=overrides.domain_name or profile.domain_name,
            banner_motd=overrides.banner_motd or profile.banner_motd,
            ntp_server=(
                overrides.ntp_server
                if overrides.ntp_server is not None
                else profile.ntp_server
            ),
            interfaces=merged_interfaces,
        )
