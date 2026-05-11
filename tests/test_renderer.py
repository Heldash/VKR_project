from app.automation.models import BaseConfigurationRequest
from app.automation.renderer import BaseConfigRenderer


def test_renderer_uses_jinja2_template_and_renders_cisco_mask_syntax():
    renderer = BaseConfigRenderer()

    result = renderer.render_commands(
        BaseConfigurationRequest(
            hostname="EDGE-R1",
            domain_name="branch.lab",
            banner_motd="Managed by NetAuto",
            ntp_server="192.0.2.10",
            interfaces=[
                {
                    "name": "GigabitEthernet0/0",
                    "description": "Transit to R2",
                    "ipv4_address": "10.0.12.1/30",
                    "enabled": True,
                }
            ],
        )
    )

    assert result[:4] == [
        "hostname EDGE-R1",
        "ip domain-name branch.lab",
        "banner motd ^Managed by NetAuto^",
        "ntp server 192.0.2.10",
    ]
    assert "interface GigabitEthernet0/0" in result
    assert " description Transit to R2" in result
    assert " ip address 10.0.12.1 255.255.255.252" in result
    assert " no shutdown" in result
