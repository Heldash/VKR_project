"""Rendering helpers for configuration generation."""

from ipaddress import ip_interface

from app.automation.models import BaseConfigurationRequest, MockDeviceRuntimeState
from app.domain.models import InterfaceSpec


class BaseConfigRenderer:
    """Builds CLI commands for previews and mocked running-config snapshots."""

    def render_commands(self, request: BaseConfigurationRequest) -> list[str]:
        commands = [
            f"hostname {request.hostname}",
            f"ip domain-name {request.domain_name}",
            f"banner motd ^{request.banner_motd}^",
        ]
        if request.ntp_server:
            commands.append(f"ntp server {request.ntp_server}")
        for interface in request.interfaces:
            commands.extend(self._render_interface_block(interface))
        return commands

    def render_running_config(self, state: MockDeviceRuntimeState) -> list[str]:
        lines = [
            f"hostname {state.hostname}",
            f"ip domain-name {state.domain_name}",
        ]
        if state.banner_motd:
            lines.append(f"banner motd ^{state.banner_motd}^")
        if state.ntp_server:
            lines.append(f"ntp server {state.ntp_server}")
        for interface in state.interfaces:
            lines.extend(self._render_interface_block(interface))
        return lines

    @staticmethod
    def _render_interface_block(interface: InterfaceSpec) -> list[str]:
        lines = [f"interface {interface.name}"]
        if interface.description:
            lines.append(f" description {interface.description}")
        if interface.ipv4_address:
            lines.append(BaseConfigRenderer._render_ipv4_address(interface.ipv4_address))
        lines.append(" no shutdown" if interface.enabled else " shutdown")
        lines.append(" exit")
        return lines

    @staticmethod
    def _render_ipv4_address(value: str) -> str:
        iface = ip_interface(value)
        return f" ip address {iface.ip} {iface.network.netmask}"
