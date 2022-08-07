import json
import boto3
import botocore
import pytest
from unittest.mock import Mock, MagicMock
from fetch_visitors.app import FetchUpdate
from botocore.exceptions import ClientError



@pytest.fixture
def event_no_ua():
    """Generates an API GW simulating a request with no "User-Agent" header anywhere"""
    return json.loads( open('events/event-no-ua.json').read() )


# For future use
sample_db = [
    ("10.0.0.1", "Mozilla/1.0 (Pam's Laptop)"),  # home connection, primary device
    ("10.0.0.2", "Mozilla/1.0 (Pam's Laptop)"),  # home connection but the dynIP changed
    ("10.0.0.1", "Webkit/2.4 - Android"),  # home connection, from mobile device
]

def put_item_mock_that_returns(**kwargs):
    resp_mock = MagicMock(spec=dict) # spec is needed to mock the json.dumps(put_item_resp) that takes place right after the op
    resp_mock.return_value = ""
    return resp_mock

def put_item_mock_that_throws_ccfe(**kwargs):
    error_response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    ccfe = botocore.exceptions.ClientError(error_response, "dummyop")
    raise ccfe

def put_item_mock_that_throws_other_clienterror(**kwargs):
    error_response = {"Error": {"Code": "StillAClientError"}}
    ce = botocore.exceptions.ClientError(error_response, "dummyop")
    raise ce

def put_item_mock_that_throws_other(**kwargs):
    raise Exception # just a generic exception, not a ClientError that could signify existence



class TestExtractIPUA:
    def test_no_useragent(self, event_no_ua):
        """
        Send a request with no User-Agent and check the response matches the expected format and error msg
        """
        fu = FetchUpdate(event_no_ua)
        with pytest.raises(Exception) as e:
            fu.extract_ip_ua()
        assert FetchUpdate.ERR_NO_UA in str(e.value)


class TestDbPutItem:

    def test_notexists_in_db(self):
        """
        :return:
        """
        fu = FetchUpdate(None)
        fu.client = Mock()
        fu.client.put_item.side_effect = put_item_mock_that_returns

        result = fu.db_putitem("dummyIP","that_returns")

        assert fu.client.put_item.called_once()
        assert result == "added"


    def test_exists_in_db(self):
        fu = FetchUpdate(None)
        fu.client = Mock()
        fu.client.put_item.side_effect = put_item_mock_that_throws_ccfe

        result = fu.db_putitem("dummyIP","dummyUA")

        assert fu.client.put_item.called_once()
        assert result == "found"

    def test_db_clienterror_fail(self):
        """
        Assessing path app.py:128-129
        :param ip:
        :param ua:
        :param exp_result:
        :return:
        """
        fu = FetchUpdate(None)
        fu.client = Mock()
        fu.client.put_item.side_effect = put_item_mock_that_throws_other_clienterror

        with pytest.raises(Exception) as e:
            result = fu.db_putitem("dummyIP","dummyUA")

        assert fu.client.put_item.called_once()


    def test_db_other_fail(self):
        """
        Assessing path app.py:131-132
        :param ip:
        :param ua:
        :param exp_result:
        :param sample_db:
        :return:
        """
        fu = FetchUpdate(None)
        fu.client = Mock()
        fu.client.put_item.side_effect = put_item_mock_that_throws_other

        with pytest.raises(Exception) as e:
            result = fu.db_putitem("dummyIP","dummyUA")

        assert fu.client.put_item.called_once()

