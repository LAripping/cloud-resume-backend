import json
from unittest.mock import patch, Mock

import boto3
import botocore
import pytest
from pytest_mock import mocker

import fetch_visitors
from fetch_visitors.app import FetchUpdate
from fetch_visitors import app
from botocore.exceptions import ClientError



@pytest.fixture
def event_no_ua():
    """Generates an API GW simulating a request with no "User-Agent" header anywhere"""
    return json.loads( open('events/event-no-ua.json').read() )



sample_db = [
    ("10.0.0.1", "Mozilla/1.0 (Pam's Laptop)"),  # home connection, primary device
    ("10.0.0.2", "Mozilla/1.0 (Pam's Laptop)"),  # home connection but the dynIP changed
    ("10.0.0.1", "Webkit/2.4 - Android"),  # home connection, from mobile device
]

def mock_put_item(**kwargs):
    ip_passed = kwargs["Item"]["IP"]["S"]
    ua_passed = kwargs["Item"]["UA"]["S"]
    if not (isinstance(ip_passed, str) and isinstance(ua_passed, str)):
        raise TypeError  # random exception, anything other than the ConditionalCheckFailedException
    elif (ip_passed, ua_passed) in TestDbPutItem.sample_db:
        return None  # no exception thrown -> Insertion Succeeded
    else:
        dynares = boto3.resource('dynamodb')
        raise dynares.meta.client.exceptions.ConditionalCheckFailedException

class mock_client:
    def put_item(**kwargs):
        return mock_put_item(**kwargs)



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

    @pytest.mark.parametrize("ip,ua,exp_result",[
        ("10.0.0.1", "Mozilla/1.0 (Pam's Laptop)", "found"),
        ("10.0.0.1", "Webkit/2.4 - Android", "found"),
        ("10.0.0.2", "Webkit/2.4 - Android", "added"),  # Pam's mobile device but after dynIP changed
        ("8.7.8.7", "Webkit/2.4 - Android", "added")  # Pam's mobile device but from 4G connection
    ])
    def test_notexists_in_db(self, ip, ua, exp_result):
        fu = FetchUpdate(None)
        fu.client = Mock()
        fu.client.put_item.return_value = {} # put_item will return anything but won't throw

        result = fu.db_putitem(ip,ua)

        assert fu.client.put_item.called_once()
        assert result == "added"

    @pytest.mark.parametrize("ip,ua,exp_result", [
        ("10.0.0.2", "Webkit/2.4 - Android", "added"),  # Pam's mobile device but after dynIP changed
        ("8.7.8.7", "Webkit/2.4 - Android", "added")    # Pam's mobile device but from 4G connection
    ])
    def test_exists_in_db(self, ip, ua, exp_result):
        fu = FetchUpdate(None)
        fu.client = Mock()
        error_response = {"Error":{"Code":"ConditionalCheckFailedException"}}
        operation_name = "whocares"
        ce = botocore.exceptions.ClientError(error_response,operation_name)
        fu.client.put_item.side_effect = ce

        result = fu.db_putitem(ip, ua)

        assert fu.client.put_item.called_once()
        assert result == "found"

    @pytest.mark.parametrize("ip,ua,exp_result", [
        ("10.0.0.2", "Webkit/2.4 - Android", "added"),  # Pam's mobile device but after dynIP changed
        ("8.7.8.7", "Webkit/2.4 - Android", "added")    # Pam's mobile device but from 4G connection
    ])
    def test_db_clienterror_fail(self, ip, ua, exp_result):
        """
        Assessing path app.py:128-129
        :param ip:
        :param ua:
        :param exp_result:
        :return:
        """
        fu = FetchUpdate(None)
        fu.client = Mock()
        error_response = {"Error":{"Code":"StillAClientError"}}
        operation_name = "whocares"
        ce = botocore.exceptions.ClientError(error_response,operation_name)
        fu.client.put_item.side_effect = ce

        with pytest.raises(Exception) as e:
            result = fu.db_putitem(ip, ua)

        assert fu.client.put_item.called_once()


    @pytest.mark.parametrize("ip,ua", [
        (42, "Mozilla/1.0 (Pam's Laptop)"),
        ("10.0.0.1", True)
    ])
    def test_db_other_fail(self, ip, ua, mocker):
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
        fu.client.put_item.side_effect = Exception  # just a generic exception, not a ClientError that could signify existence

        with pytest.raises(Exception) as e:
            result = fu.db_putitem(ip, ua)

        assert fu.client.put_item.called_once()

