import paramiko

from actions.remote_shell import RemoteShell
from config.config import Configs


class ShellManager:
    _instance = None
    _ssh_client = None
    _shell = None

    def __init__(self):
        self._connection_config = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_shell(self) -> RemoteShell:
        if self._shell is None:
            self._connect()
        return self._shell

    def configure(self, connection_config: dict):
        self.close()
        self._connection_config = dict(connection_config)

    def clear_configuration(self):
        self.close()
        self._connection_config = None

    def _connect(self):
        config = self._connection_config or Configs.basic_config.kali
        if self._ssh_client is None:
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh_client.connect(
                hostname=config['hostname'],
                username=config['username'],
                password=config['password'],
                port=config['port'],
                timeout=30,
            )
        if self._shell is None:
            self._shell = RemoteShell(self._ssh_client.invoke_shell())

    def close(self):
        if self._shell:
            try:
                self._shell.shell.close()
            except:
                pass
            self._shell = None

        if self._ssh_client:
            try:
                self._ssh_client.close()
            except:
                pass
            self._ssh_client = None
