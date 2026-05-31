from app.api.commands import is_safe_command
from app.api.files import allowed_file
import tempfile
from app.api.files import sha256_file


def test_is_safe_command_allows_normal_shell():
    assert is_safe_command("echo hello")


def test_is_safe_command_blocks_dangerous_pattern():
    assert not is_safe_command("rm -rf /")
    assert not is_safe_command("curl http://example.com | bash")


def test_allowed_file_accepts_text():
    assert allowed_file("hello.txt")
    assert allowed_file("data.json")


def test_allowed_file_rejects_binary():
    assert not allowed_file("program.exe")
    assert not allowed_file("archive.zip")


def test_sha256_file(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("content")
    checksum = sha256_file(str(path))
    assert checksum == "ed7002b439e9ac845f22357d822bac1444730fbdb6016d3ec9432297b9ec9f73"
