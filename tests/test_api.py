import json

import pytest


class TestHealth:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestParseEndpoint:
    @pytest.mark.parametrize("fixture_name,language,expected_type", [
        ("test.py", "Python", "Module"),
        ("test.kt", "Kotlin", "Module"),
        ("test.dart", "Dart", "Module"),
    ])
    async def test_parse_returns_units(self, client, load_fixture, fixture_name, language, expected_type):
        payload = {
            "source_text": load_fixture(fixture_name),
            "file_path": f"src/example.{fixture_name.split('.')[-1]}",
            "language": language,
        }
        resp = await client.post("/parse", json=payload)
        assert resp.status_code == 200
        result = resp.json()
        assert result["language"] == language
        assert result["warnings"] == []
        assert len(result["units"]) > 0
        assert result["units"][0]["type"] == expected_type

    async def test_parse_invalid_language(self, client):
        payload = {
            "source_text": "hello",
            "file_path": "test.rb",
            "language": "Ruby",
        }
        resp = await client.post("/parse", json=payload)
        assert resp.status_code == 422

    async def test_parse_empty_source(self, client):
        payload = {
            "source_text": "",
            "file_path": "empty.py",
            "language": "Python",
        }
        resp = await client.post("/parse", json=payload)
        assert resp.status_code == 200
        result = resp.json()
        assert len(result["units"]) == 1
        assert result["units"][0]["type"] == "Module"

    async def test_parse_syntax_error_returns_warnings(self, client):
        payload = {
            "source_text": "def broken(:\n  pass",
            "file_path": "bad.py",
            "language": "Python",
        }
        resp = await client.post("/parse", json=payload)
        assert resp.status_code == 200
        result = resp.json()
        assert len(result["warnings"]) > 0
        assert result["units"] == []

    async def test_parse_preserves_file_path(self, client):
        payload = {
            "source_text": "x = 1",
            "file_path": "some/deep/nested/path/module.py",
            "language": "Python",
        }
        resp = await client.post("/parse", json=payload)
        assert resp.status_code == 200
        assert resp.json()["filePath"] == "some/deep/nested/path/module.py"

    async def test_request_size_limit_returns_clear_error(self, client):
        huge_source = "x = 1\n" * (10 * 1024 * 1024)
        payload = json.dumps({
            "source_text": huge_source,
            "file_path": "huge.py",
            "language": "Python",
        })
        resp = await client.post(
            "/parse",
            content=payload.encode(),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 413
        assert "maximum" in resp.json()["detail"].lower()