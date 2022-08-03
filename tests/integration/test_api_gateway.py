import os
import boto3
import requests
from urllib3 import connection
from unittest import TestCase
from fetch_visitors.app import FetchUpdate
from datetime import datetime

# One class - Many `test_*` functions (cases)


class TestApiGateway(TestCase):
    api_endpoint: str

    @classmethod
    def get_stack_name(cls) -> str:
        stack_name = os.environ.get("STACK_NAME")
        if not stack_name:
            raise Exception(
                "Cannot find env var STACK_NAME. \n"
                "Please setup this environment variable with the stack name where we are running integration tests."
            )
        return stack_name

    def get_db_count(self) -> int:
        scan_resp = self.client_dyn.scan(
            TableName='VisitorsSam',
            Select='COUNT',
            FilterExpression="test <> :istest",
            ExpressionAttributeValues={
                ":istest": {"BOOL": True}
            }
        )
        return scan_resp["Count"]

    def delete_db_item(self, myIP: str, randUA: str):
        resp = self.client_dyn.delete_item(
            TableName='VisitorsSam',
            Key={'IP': {"S": myIP}, 'UA': {"S": randUA}}
        )
        self.assertEquals(resp["ResponseMetadata"]["HTTPStatusCode"], 200, "DeleteItem request failed!")

    def setUp(self) -> None:
        """
        (The setUp() method Executes before any test_* case/method to create/load any fixtures)
        Here, it's used to extract the api_endpoint, using boto client to parse the Outputs for the ApiCreated URL
        Needs the env variable STACK_NAME to filter the API response
        Needs also AWS IAM credentials to be configured - use AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars
        """

        stack_name = TestApiGateway.get_stack_name()
        self.client_cn  = boto3.client("cloudformation", region_name="eu-west-2")
        self.client_dyn = boto3.client('dynamodb', region_name="eu-west-2")
        try:
            response = self.client_cn.describe_stacks(StackName=stack_name)
        except Exception as e:
            raise Exception(
                f"Cannot find stack {stack_name}. \n" f'Please make sure stack with the name "{stack_name}" exists.'
            ) from e

        stacks = response["Stacks"]
        stack_outputs = stacks[0]["Outputs"]
        api_outputs = [output for output in stack_outputs if output["OutputKey"] == "ApiCreated"]
        self.assertTrue(api_outputs, f"Cannot find output ApiCreated in stack {stack_name}")
        self.api_endpoint = api_outputs[0]["OutputValue"]

    def test_api_gateway(self):
        """
        Call the API Gateway endpoint created and check the response matches the expected non-error format
        """

        response = requests.get(self.api_endpoint)
        self.assertEqual(response.status_code, 200, "Response should be 200 OK!")
        self.assertIsInstance(response.json(),dict, "Response should be JSON!")
        self.assertIn(response.json()['result'],("added","found"), "Result should be 'added' or 'found'!")
        self.assertIsInstance(response.json()['visitors'],int, "Visitor count should be a number!")

    # def test_no_useragent(self):
    #     """
    #     Send a request with no User-Agent and check the response matches the expected format and error msg
    #     """
    #
    #     # Monkeypatch urllib3.request to only send headers we explicitly specify. No defaults
    #     def request(self, method, url, body=None, headers=None):
    #         if headers is None:
    #             headers = {}
    #         else:
    #             headers = headers.copy()
    #             print("Using patched request obj. Headers=%s"+str(headers))
    #         super(connection.HTTPConnection, self).request(method, url, body=body, headers=headers)
    #
    #     connection.HTTPConnection.request = request
    #
    #     response = requests.get(self.api_endpoint, headers={"User-Agent": None})
    #     self.assertEqual(response.status_code, 200, "Response should be 200 OK!")
    #     self.assertIsInstance(response.json(),dict, "Response should be JSON!")
    #     self.assertEqual(response.json()['result'],"error", "Result should be 'error'!")
    #     self.assertEqual(response.json()['error'],FetchUpdate.ERR_NO_UA, "Visitor count should be a number!")

    def test_random_new_useragent(self):
        """
        Send a request with a time-based random User-Agent and check if it's added, both through the API and in the DB
        """

        # Arrange
        oldcount = self.get_db_count()
        randUA = str(datetime.now(tz=None)) # if you find this being repeated / gets more complicated, isolate into a fixture
        myIP = requests.get('http://ifconfig.me').text

        # Act
        response = requests.get(self.api_endpoint, headers={"User-Agent": randUA})

        # Assert API
        self.assertEqual(response.status_code, 200, "Response should be 200 OK!")
        self.assertIsInstance(response.json(), dict, "Response should be JSON!")
        self.assertEqual(response.json()['result'], "added", "Result should be 'added'!")

        # Assert DB
        newcount = self.get_db_count()
        self.assertEqual(newcount, oldcount+1, "DB item should be increased by one!")

        # Cleanup DB
        self.delete_db_item(myIP,randUA)

    def test_no_timeout(self):
        """
        Ensure no timeout after 10" occur neither on the server nor on the client
        """
        TIMEOUT_SEC = 10

        try:
            response = requests.get(self.api_endpoint, timeout=TIMEOUT_SEC)
        except requests.exceptions.Timeout:
            self.fail("Client timed out!")

        self.assertNotEqual(response.status_code, 504, "Server timed out!")
