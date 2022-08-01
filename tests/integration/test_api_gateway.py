import os
import boto3
import requests
from unittest import TestCase


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


    def setUp(self) -> None:
        """
        Use boto client to find out the URL of the ApiCreated from the Outputs

        Needs the env variable STACK_NAME to filter the API response

        Needs also AWS IAM credentials to be configured
        (use AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars)
        """

        stack_name = TestApiGateway.get_stack_name()
        client = boto3.client("cloudformation", region_name="eu-west-2")
        try:
            response = client.describe_stacks(StackName=stack_name)
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
        self.assertIsInstance(response.json(),dict)
        self.assertIn(response.json()['result'],("added","found"))
        self.assertIsInstance(response.json()['visitors'],int)
