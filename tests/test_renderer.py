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


def test_renderer_uses_juniper_template_for_junos_platform():
    renderer = BaseConfigRenderer()

    result = renderer.render_commands(
        BaseConfigurationRequest(
            hostname="EDGE-J1",
            domain_name="branch.lab",
            banner_motd="Managed by NetAuto",
            ntp_server="192.0.2.10",
            interfaces=[
                {
                    "name": "ge-0/0/0",
                    "description": "Transit to R2",
                    "ipv4_address": "10.0.12.1/30",
                    "enabled": True,
                }
            ],
        ),
        platform="juniper_junos",
    )

    assert result[:4] == [
        "set system host-name EDGE-J1",
        "set system domain-name branch.lab",
        'set system login message "Managed by NetAuto"',
        "set system ntp server 192.0.2.10",
    ]
    assert 'set interfaces ge-0/0/0 description "Transit to R2"' in result
    assert "set interfaces ge-0/0/0 unit 0 family inet address 10.0.12.1/30" in result
    assert "delete interfaces ge-0/0/0 disable" in result


def test_renderer_uses_huawei_template_for_vrp_platform():
    renderer = BaseConfigRenderer()

    result = renderer.render_commands(
        BaseConfigurationRequest(
            hostname="EDGE-H1",
            domain_name="branch.lab",
            interfaces=[
                {
                    "name": "GigabitEthernet0/0/1",
                    "description": "Transit to R2",
                    "ipv4_address": "10.0.12.1/30",
                    "enabled": False,
                }
            ],
        ),
        platform="huawei_vrp",
    )

    assert result[:2] == [
        "sysname EDGE-H1",
        "ip domain-name branch.lab",
    ]
    assert "interface GigabitEthernet0/0/1" in result
    assert " description Transit to R2" in result
    assert " ip address 10.0.12.1 255.255.255.252" in result
    assert " shutdown" in result
    assert " quit" in result
