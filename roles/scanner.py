from typing import ClassVar

from prompts.scanner_prompt import ScannerPrompt
from roles.role import Role


class Scanner(Role):

    name: str = "Vulnerability Scanner"

    goal: str = (
        "Based on the reconnaissance results, "
        "further enumeration and check for vulnerabilities and misconfigurations in the target."
    )

    tools: str = (
        "Nikto, "
        "Curl, "
        "Dirb, "
        "Whatweb, "
        "WPScan, "
        "Sqlmap, "
        "ExploitDB, "
        "Wapiti, "
        "Aircrack-ng, "
        "Webshells, "
        "Weevely, " 
        "Tshark, "
        "Nmap(with NSE scripts)."
    )

    prompt: ClassVar[ScannerPrompt] = ScannerPrompt
