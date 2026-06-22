from actions.remote_shell import RemoteShell, SSHOutputHandler


class ChunkedChannel:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def recv_ready(self):
        return bool(self.chunks)

    def recv(self, _size):
        return self.chunks.pop(0)

    def send(self, _data):
        self.sent = _data
        return None


def test_extract_framed_output_includes_stdout_and_exit_code():
    output = "student\nuid=1000(student)\n__VULNBOT_DONE_test__:0\nroot@kali:# "

    assert RemoteShell._extract_framed_output(output, "__VULNBOT_DONE_test__") == (
        "student\nuid=1000(student)\n[exit_code: 0]"
    )


def test_extract_framed_output_makes_silent_success_observable():
    output = "\r\n__VULNBOT_DONE_test__:0\r\nroot@kali:# "

    assert RemoteShell._extract_framed_output(
        output, "__VULNBOT_DONE_test__"
    ) == "[exit_code: 0]"


def test_extract_framed_output_preserves_interactive_prompt_without_marker():
    output = "student@192.168.1.0's password: "

    assert RemoteShell._extract_framed_output(
        output, "__VULNBOT_DONE_test__"
    ) == output


def test_receive_data_consumes_prompt_arriving_after_completion_marker():
    marker = "__VULNBOT_DONE_test__"
    channel = ChunkedChannel([
        f"output\r\n{marker}:0\r\n".encode(),
        b"root@kali_master:~# ",
    ])

    output = SSHOutputHandler.receive_data(
        channel, timeout=1.0, completion_marker=marker
    )

    assert "output" in output
    assert marker in output
    assert output.endswith("root@kali_master:~# ")


def test_clean_terminal_output_preserves_text_between_osc_sequences():
    output = (
        "\x1b]3008;start=command\x1b\\"
        "SHELL_OK\r\n__VB_DONE__:0\r\n"
        "\x1b]3008;end=command\x1b\\"
    )

    assert SSHOutputHandler.clean_terminal_output(output) == (
        "SHELL_OK\r\n__VB_DONE__:0\r\n"
    )


def test_send_input_does_not_append_shell_completion_command():
    shell = RemoteShell.__new__(RemoteShell)
    shell.shell = ChunkedChannel([b"student@target:~$ "])

    output = shell.send_input("password")

    assert shell.shell.sent == "password\n"
    assert output == "student@target:~$ "
