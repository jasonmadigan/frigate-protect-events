from unittest.mock import patch, MagicMock

from frigate_protect_events.snapshot import fetch_snapshot


class TestFetchSnapshot:
    @patch("frigate_protect_events.snapshot.requests.get")
    def test_returns_jpeg_bytes(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\xff\xd8\xff\xe0JFIF"
        mock_get.return_value = mock_resp

        result = fetch_snapshot("192.168.1.5", "evt-123")
        assert result == b"\xff\xd8\xff\xe0JFIF"
        mock_get.assert_called_once_with(
            "http://192.168.1.5:5000/api/events/evt-123/snapshot.jpg",
            timeout=10,
        )

    @patch("frigate_protect_events.snapshot.requests.get")
    def test_returns_none_on_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = fetch_snapshot("192.168.1.5", "evt-123")
        assert result is None

    @patch("frigate_protect_events.snapshot.requests.get")
    def test_returns_none_on_connection_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.ConnectionError("refused")

        result = fetch_snapshot("192.168.1.5", "evt-123")
        assert result is None

    def test_returns_none_when_no_host(self):
        result = fetch_snapshot(None, "evt-123")
        assert result is None
