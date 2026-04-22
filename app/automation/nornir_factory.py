"""Constructs Nornir instances backed by the selected inventory."""

from nornir.core import Nornir
from nornir.core.inventory import ConnectionOptions, Defaults, Host, Inventory
from nornir.plugins.runners import SerialRunner

from app.core.config import settings
from app.domain.models import MockRouter


def build_nornir(devices: list[MockRouter]) -> Nornir:
    """Creates a serial Nornir runner over the current inventory."""

    defaults = Defaults(
        username=settings.device_username,
        password=settings.device_password,
        port=settings.device_port,
        data={"inventory_backend": settings.inventory_backend},
        connection_options={
            "netmiko": ConnectionOptions(
                username=settings.device_username,
                password=settings.device_password,
                port=settings.device_port,
                extras={"secret": settings.device_secret} if settings.device_secret else {},
            )
        },
    )
    hosts = {
        device.name: Host(
            name=device.name,
            hostname=device.management_ip,
            port=device.port,
            username=device.username,
            password=device.password,
            platform=device.platform,
            data={
                "vendor": device.vendor,
                "role": device.role,
                "site": device.site,
                "status": device.status,
                "secret": device.secret,
            },
            connection_options={
                "netmiko": ConnectionOptions(
                    hostname=device.management_ip,
                    port=device.port,
                    username=device.username,
                    password=device.password,
                    platform=device.platform,
                    extras={"secret": device.secret} if device.secret else {},
                )
            },
            defaults=defaults,
        )
        for device in devices
    }
    inventory = Inventory(hosts=hosts, defaults=defaults)
    return Nornir(inventory=inventory, runner=SerialRunner())
