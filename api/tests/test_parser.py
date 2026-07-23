import json

from pipeline import parser


def test_parse_apache_common():
    line = '127.0.0.1 - - [10/Oct/2023:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326'
    p = parser.parse_line(line)
    assert p.log_format == "access"
    assert p.ip == "127.0.0.1"
    assert p.status_code == 200
    assert p.level == "INFO"
    assert p.message == "GET /index.html"


def test_parse_nginx_with_request_time():
    line = (
        '192.168.1.1 - - [10/Oct/2023:13:55:36 +0000] "POST /api/pay HTTP/1.1" '
        '503 0 "-" "Mozilla/5.0" 1.250'
    )
    p = parser.parse_line(line)
    assert p.status_code == 503
    assert p.level == "ERROR"
    assert p.response_time_ms == 1250.0


def test_parse_json_log():
    line = json.dumps(
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "level": "warn",
            "message": "slow query",
            "status": 404,
            "latency_ms": 88,
            "client_ip": "8.8.8.8",
            "service": "api",
        }
    )
    p = parser.parse_line(line)
    assert p.log_format == "json"
    assert p.level == "WARN"
    assert p.status_code == 404
    assert p.response_time_ms == 88
    assert p.ip == "8.8.8.8"
    assert p.source == "api"


def test_json_level_inferred_from_status():
    line = json.dumps({"timestamp": "2024-01-01T00:00:00Z", "message": "x", "status": 500})
    assert parser.parse_line(line).level == "ERROR"


def test_parse_syslog():
    line = "Oct 10 13:55:36 web01 nginx[1234]: connection refused ERROR"
    p = parser.parse_line(line)
    assert p.log_format == "syslog"
    assert p.source == "nginx"
    assert p.level == "ERROR"
    assert "connection refused" in p.message


def test_unparseable_returns_none():
    assert parser.parse_line("this is not a log line !!!") is None
    assert parser.parse_line("   ") is None


def test_detect_format_and_parse_text():
    text = "\n".join(
        json.dumps({"timestamp": "2024-01-01T00:00:00Z", "message": "a", "status": 200})
        for _ in range(5)
    )
    assert parser.detect_format(text) == "json"
    assert len(parser.parse_text(text)) == 5


def test_level_from_status():
    assert parser.level_from_status(200) == "INFO"
    assert parser.level_from_status(404) == "WARN"
    assert parser.level_from_status(500) == "ERROR"
    assert parser.level_from_status(None) == "INFO"
