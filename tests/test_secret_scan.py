from tools.secret_scan import added_lines, scan_lines, scan_names

# Every fake key below is built at run time so this file never holds one itself.
FAKE_SK = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2m3"
FAKE_LONG = "Zx9" * 10


def test_refuses_known_key_shapes():
    assert scan_lines([("a.py", f'client = OpenAI(api_key="{FAKE_SK}")')], None)
    assert scan_lines([("a.py", "-----BEGIN RSA " + "PRIVATE KEY-----")], None)
    assert scan_lines([("a.py", f"headers = {{'Authorization': 'Bearer {FAKE_LONG}'}}")], None)


def test_refuses_a_key_name_set_to_a_long_literal():
    assert scan_lines([("a.py", f'META_API_KEY = "{FAKE_LONG}"')], None)
    assert scan_lines([("cfg.ini", f"META_API_KEY={FAKE_LONG}")], None)


def test_refuses_the_real_key_anywhere():
    real = "mk-" + "q" * 30
    assert scan_lines([("notes.md", f"my key is {real} ok")], real)


def test_allows_ordinary_code():
    lines = [
        ("a.py", 'key = os.environ.get("META_API_KEY")'),
        ("a.py", '[Environment]::SetEnvironmentVariable("META_API_KEY", "<your key>", "User")'),
        ("a.py", "token_count = count_tokens(text)"),
        ("a.py", 'password_hint = "short"'),
    ]
    assert scan_lines(lines, None) == []


def test_allow_marker():
    assert scan_lines([("a.py", f'example = "{FAKE_SK}"  # secret-scan: ok')], None) == []


def test_refuses_env_files_but_not_the_example():
    assert scan_names([".env", "config/prod.env", ".env.local"])
    assert scan_names([".env.example", "app/environment.py"]) == []


def test_added_lines_reads_a_diff():
    diff = "+++ b/x.py\n@@ -0,0 +1 @@\n+hello\n-gone\n"
    assert added_lines(diff) == [("x.py", "hello")]
