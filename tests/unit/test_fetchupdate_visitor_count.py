import json
import pytest
from fetch_visitors.app import FetchUpdate


@pytest.fixture()
def event_no_ua():
    """Generates an API GW simulating a request with no "User-Agent" header anywhere"""
    return json.loads( open('events/event-no-ua.json').read() )


class TestExtractIPUA:
    def test_no_useragent(self, event_no_ua):
        """
        Send a request with no User-Agent and check the response matches the expected format and error msg
        """
        fu = FetchUpdate(event_no_ua)
        with pytest.raises(Exception) as e:
            fu.extract_ip_ua()
        assert FetchUpdate.ERR_NO_UA in str(e.value)

        # assert "location" in data.dict_keys()
