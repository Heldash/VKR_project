"""Rendering helpers for configuration generation."""

from pathlib import Path
from ipaddress import ip_interface

from jinja2 import Environment, FileSystemLoader

from app.automation.models import BaseConfigurationRequest, MockDeviceRuntimeState
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

    def render_commands(self, request: BaseConfigurationRequest) -> list[str]:
        return self._render_document(
            hostname=request.hostname,
            domain_name=request.domain_name,
            banner_motd=request.banner_motd,
            ntp_server=request.ntp_server,
            interfaces=request.interfaces,
        )

    def render_running_config(self, state: MockDeviceRuntimeState) -> list[str]:
        return self._render_document(
            hostname=state.hostname,
            domain_name=state.domain_name,
            banner_motd=state.banner_motd,
            ntp_server=state.ntp_server,
            interfaces=state.interfaces,
        )

    @staticmethod
    def _render_interface_payload(interface: InterfaceSpec) -> dict[str, str | bool | None]:
        return {
            "name": interface.name,
            "description": interface.description or None,
            "ipv4_address": BaseConfigRenderer._render_ipv4_address(interface.ipv4_address)
            if interface.ipv4_address
            else None,
            "enabled": interface.enabled,
        }

    def _render_document(
        self,
        *,
        hostname: str,
        domain_name: str,
        banner_motd: str | None,
        ntp_server: str | None,
        interfaces: list[InterfaceSpec],
    ) -> list[str]:
        template = _JINJA_ENV.get_template("base_config.j2")
        rendered = template.render(
            hostname=hostname,
            domain_name=domain_name,
            banner_motd=banner_motd,
            ntp_server=ntp_server,
            interfaces=[self._render_interface_payload(interface) for interface in interfaces],
        )
        return [line.rstrip() for line in rendered.splitlines() if line.strip()]

    @staticmethod
    def _render_ipv4_address(value: str) -> str:
        iface = ip_interface(value)
        return f"ip address {iface.ip} {iface.network.netmask}"
