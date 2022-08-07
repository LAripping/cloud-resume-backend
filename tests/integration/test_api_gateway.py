import os
import boto3
import pytest
import requests
from datetime import datetime


@pytest.fixture(scope="module")
def stack_name() -> str:
    stack_name = os.environ.get("STACK_NAME")
    if not stack_name:
        raise Exception(
            "Cannot find env var STACK_NAME. \n"
            "Please setup this environment variable with the stack name where we are running integration tests."
        )
    return stack_name


@pytest.fixture(scope="module")
def api_endpoint(stack_name, boto_client_cn) -> str:
    try:
        response = boto_client_cn.describe_stacks(StackName=stack_name)
    except Exception as e:
        raise Exception(
            f"Cannot find stack {stack_name}. \n" f'Please make sure stack with the name "{stack_name}" exists.'
        ) from e

    stack_outputs = response["Stacks"][0]["Outputs"]
    api_outputs = [output for output in stack_outputs if output["OutputKey"] == "ApiCreated"]
    assert api_outputs, f"Cannot find output ApiCreated in stack {stack_name}"
    return api_outputs[0]["OutputValue"]


@pytest.fixture(scope="module")  # expensive so re-use for all tests in this module
def boto_client_cn() -> None:
    """
    Needs AWS IAM credentials to be configured - use AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars
    """
    return boto3.client("cloudformation", region_name="eu-west-2")


@pytest.fixture(scope="module")  # expensive so re-use for all tests in this module
def boto_client_dyn() -> None:
    """
    Needs AWS IAM credentials to be configured - use AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars
    """
    return boto3.client("dynamodb", region_name="eu-west-2")


def get_db_count(client_dyn):
    resp = client_dyn.scan(
        TableName='VisitorsSam',
        Select='COUNT',
        FilterExpression="test <> :istest",
        ExpressionAttributeValues={
            ":istest": {"BOOL": True}
        }
    )
    return resp["Count"]


def delete_db_item(client_dyn, myIP, randUA):
    resp = client_dyn.delete_item(
        TableName='VisitorsSam',
        Key={'IP': {"S": myIP}, 'UA': {"S": randUA}}
    )
    assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200


class TestApiGateway():
    def test_sanity(self, api_endpoint):
        """
        Call the API Gateway endpoint created and check the response matches the expected non-error format
        """

        response = requests.get(api_endpoint)
        assert response.status_code == 200
        assert isinstance(response.json(), dict)
        assert response.json()['result'] in ("added", "found")
        assert isinstance(response.json()['visitors'], int)

    def test_random_new_useragent(self, api_endpoint, boto_client_dyn):
        """
        Send a request with a time-based random User-Agent and check if it's added, both through the API and in the DB
        """

        # Arrange
        oldcount = get_db_count(boto_client_dyn)
        randUA = str(
            datetime.now(tz=None))  # if you find this being repeated / gets more complicated, isolate into a fixture
        myIP = requests.get('http://ifconfig.me').text

        # Act
        response = requests.get(api_endpoint, headers={"User-Agent": randUA})

        # Assert API
        assert response.status_code == 200
        assert isinstance(response.json(), dict)
        assert response.json()['result'] == "added"

        # Assert DB
        newcount = get_db_count(boto_client_dyn)
        assert newcount == oldcount + 1

        # Cleanup DB
        delete_db_item(boto_client_dyn, myIP, randUA)

    def test_no_timeout(self, api_endpoint):
        """
        Ensure no timeout after 10" occur neither on the server nor on the client
        """
        TIMEOUT_SEC = 10

        try:
            response = requests.get(api_endpoint, timeout=TIMEOUT_SEC)
            assert response.status_code != 504, "Server timed out!"
        except requests.exceptions.Timeout:
            pytest.fail("Client timed out!")
