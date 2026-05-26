"""Rendering helpers for configuration generation."""

from ipaddress import ip_interface
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.automation.models import BaseConfigurationRequest, MockDeviceRuntimeState
from app.automation.platform_profiles import get_platform_profile
from app.domain.models import InterfaceSpec

_TEMPLATES_DIR = Path(__file__).with_name("templates")
_JINJA_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


class BaseConfigRenderer:
    """Builds CLI commands for previews and mocked running-config snapshots."""

    def render_commands(
        self,
        request: BaseConfigurationRequest,
        platform: str = "cisco_ios",
    ) -> list[str]:
        return self._render_document(
            platform=platform,
            hostname=request.hostname,
            domain_name=request.domain_name,
            banner_motd=request.banner_motd,
            ntp_server=request.ntp_server,
            interfaces=request.interfaces,
        )

    def render_running_config(
        self,
        state: MockDeviceRuntimeState,
        platform: str = "cisco_ios",
    ) -> list[str]:
        return self._render_document(
            platform=platform,
            hostname=state.hostname,
            domain_name=state.domain_name,
            banner_motd=state.banner_motd,
            ntp_server=state.ntp_server,
            interfaces=state.interfaces,
        )

    @staticmethod
    def _render_interface_payload(
        interface: InterfaceSpec,
        platform: str,
    ) -> dict[str, str | bool | None]:
        profile = get_platform_profile(platform)
        return {
            "name": interface.name,
            "description": interface.description or None,
            "ipv4_address": BaseConfigRenderer._render_ipv4_address(
                interface.ipv4_address,
                address_style=profile.interface_address_style,
            )
            if interface.ipv4_address
            else None,
            "enabled": interface.enabled,
        }

    def _render_document(
        self,
        *,
        platform: str,
        hostname: str,
        domain_name: str,
        banner_motd: str | None,
        ntp_server: str | None,
        interfaces: list[InterfaceSpec],
    ) -> list[str]:
        template = _JINJA_ENV.get_template(get_platform_profile(platform).template_name)
        rendered = template.render(
            hostname=hostname,
            domain_name=domain_name,
            banner_motd=banner_motd,
            ntp_server=ntp_server,
            interfaces=[
                self._render_interface_payload(interface, platform)
                for interface in interfaces
            ],
        )
        return [line.rstrip() for line in rendered.splitlines() if line.strip()]

    @staticmethod
    def _render_ipv4_address(value: str, address_style: str = "mask") -> str:
        iface = ip_interface(value)
        if address_style == "cidr":
            return value
        return f"ip address {iface.ip} {iface.network.netmask}"
