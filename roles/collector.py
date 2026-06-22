from typing import ClassVar

from prompts.collector_prompt import CollectorPrompt
from roles.role import Role


class Collector(Role):
    name: str = "Information Collection"

    goal: str = (
        "Perform a full scan of the target to identify all open ports and services."
    )

    tools: str = (
        "Nmap, "
        "Curl, "
        "Wget, "
        "Tcpdump, "
        "Whois, "
        "Dmitry, "
        "Dnsenum, "
        "Netdiscover, "
        "Amap, "
        "Enum4linux, "
        "Smbclient, "
        "Amass, "
        "SSLscan, "
        "SpiderFoot, "
        "Fierce."
    )

    prompt: ClassVar[CollectorPrompt] = CollectorPrompt
