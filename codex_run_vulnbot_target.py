from rich.console import Console

from actions.shell_manager import ShellManager
from db.models.session_model import Session
from db.repository.session_repository import add_session_to_db
from roles.collector import Collector
from utils.log_common import RoleType


TARGET = "http://222.201.144.177:18080/"


def main():
    console = Console()
    description = (
        "Authorized penetration test against my own test target "
        f"{TARGET}. Perform non-destructive reconnaissance and vulnerability "
        "validation only. Do not persist access, do not exfiltrate sensitive "
        "data, do not modify server state beyond minimal proof-of-vulnerability "
        "checks, and avoid high-volume brute force or denial-of-service actions. "
        "Report findings, evidence, and safe reproduction steps."
    )
    #Authorized penetration test against my own test target http://222.201.144.177:18080/. Perform non-destructive reconnaissance and vulnerability validation only. Do not persist access, do not exfiltrate sensitive data, do not modify server state beyond minimal proof-of-vulnerability checks, and avoid high-volume brute force or denial-of-service actions. Report findings, evidence, and safe reproduction steps.
    session = Session(
        current_role_name=RoleType.COLLECTOR.value,
        init_description=description,
        current_planner_id="",
        history_planner_ids=[],
    )

    try:
        Collector(console=console, max_interactions=50).run(session)
    finally:
        session.name = "codex-authorized-test-222.201.144.177-18080"
        add_session_to_db(session_data=session)
        ShellManager.get_instance().close()


if __name__ == "__main__":
    main()
