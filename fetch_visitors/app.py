import json
import boto3
import logging

import botocore

log = logging.getLogger("lambda-logger") # specify a name to ignore DEBUG messages from all other loggers
log.setLevel(logging.DEBUG)


def lambda_handler(event, context):
    """
    Processes client info (UA/IP) and adds them to the DB if they don't exist

    Parameters:
        event (dict): the JSON input
        context (dict): ?

    Returns:
        dict: A dict with keys
            result (str): "added|found|error"
            visitors (int): N
            error (str): Stringified exception message if thrown.

            This will be passed to ``json.dumps``
            https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html#python-handler-return
    """

    result = ""
    count = -1
    errorMsg = None
    fu = FetchUpdate(event)
    try:
        ip, ua = fu.extract_ip_ua()
        result = fu.db_putitem(ip, ua)
        count = fu.db_scan()
    except Exception as e:
        errorMsg = str(e)
    finally:
        return fu.send_resp(result, count, errorMsg)


class FetchUpdate:
    """
    Runner class to perform the ops we need and save internal state.
    Consists of 4 self-explanatory Methods executing one step each, as per the Single Responsibility Principle (SRP)

    Methods
    -------
        extract_ip_ua():
        db_putitem():
        db_scan():
        send_resp():
    """

    ERR_NO_IP = "Couldn't extract source IP! Skipping insertion"
    ERR_NO_UA = "Couldn't extract UA! Skipping insertion"
    ERR_PUT_ITEM = "Unexpected error while putting item: %s"
    ERR_SCAN = "Unexpected error while scanning DB: %s"

    def __init__(self, event):
        self.event = event
        self.client = boto3.client('dynamodb', region_name='eu-west-2')
        self.dynamodb = boto3.resource('dynamodb', region_name='eu-west-2')  # needed for the exception

    def extract_ip_ua(self) -> tuple:
        """
        Step 1: Try recursively (TODO deterministically)
        to get the the requestor's source IPv4 address and User-Agent, by just walking over
        all the places these could be found in
        :return: (ip,ua) a 2-tuple of strings if found
        :rtype: tuple
        :raises: Exception when IP/UA can't be found
        """
        log.debug("Event object passed (as JSON):\n%s", json.dumps(self.event))
        # friendly for copy(from logs)-paste(into a new events/event.json file)

        if ("requestContext" in self.event) \
                and ("http" in self.event["requestContext"]) \
                and ("sourceIp" in self.event["requestContext"]["http"]):
            ip = self.event["requestContext"]["http"]["sourceIp"]
        elif ("requestContext" in self.event) \
                and ("identity" in self.event["requestContext"]) \
                and ("sourceIp" in self.event["requestContext"]["identity"]):
            ip = self.event["requestContext"]["identity"]["sourceIp"]
        else:
            log.error(FetchUpdate.ERR_NO_IP)
            raise Exception(FetchUpdate.ERR_NO_IP)

        if ("requestContext" in self.event) \
                and ("http" in self.event["requestContext"]) \
                and ("userAgent" in self.event["requestContext"]["http"]):
            ua = self.event["requestContext"]["http"]["userAgent"]
        elif ("requestContext" in self.event) \
                and ("identity" in self.event["requestContext"]) \
                and ("userAgent" in self.event["requestContext"]["identity"]):
            ua = self.event["requestContext"]["identity"]["userAgent"]
        elif ("headers" in self.event) \
                and ("User-Agent" in self.event["headers"]):
            ua = self.event["headers"]["User-Agent"]
        else:
            log.error(FetchUpdate.ERR_NO_UA)
            raise Exception(FetchUpdate.ERR_NO_UA)

        log.info("Successfully extracted IP (%s) and UA (%s)", ip, ua)
        return ip, ua

    def db_putitem(self, ip, ua) -> str:
        """
        Step 2: Try to add visitor info to DB if not exists

        :return: The result of the database insertion (added|found) OR throws
        :rtype: str
        :raises: Exception when PutItem operation fails
        """

        try:
            putitem_resp = self.client.put_item(
                TableName='VisitorsSam',  # TODO extract TBL_NAME constant
                Item={
                    "UA": {"S": ua},
                    "IP": {"S": ip}
                },
                ConditionExpression='attribute_not_exists(IP) and attribute_not_exists(UA)'
            )
            log.debug("put_item response: %s", json.dumps(putitem_resp, indent=2))
            log.info("Visitor details added to the database")
            result = "added"
        except botocore.exceptions.ClientError as ce:
            if ce.response['Error']['Code'] == 'ConditionalCheckFailedException':
                log.info("Visitor details already in the database. Not added")
                result = "found"
            else:
                log.error(FetchUpdate.ERR_PUT_ITEM, str(ce))
                raise ce
        except Exception as e:
            log.error(FetchUpdate.ERR_PUT_ITEM, str(e))  # here we only log FetchUpdate.ERR_PUT_ITEM,
            raise e  # ...and not specify it, as we're interested in the orig msg

        return result

    def db_scan(self) -> int:
        """
        Step 3: Query DB for the number of total visitors seen

        :return: The number of items found in the DB
        :rtype: int
        """
        try:
            scan_resp = self.client.scan(
                TableName='VisitorsSam',
                Select='COUNT',
                FilterExpression="test <> :istest",
                ExpressionAttributeValues={
                    ":istest": {"BOOL": True}
                }
            )
            log.debug("scan response: %s", json.dumps(scan_resp, indent=2))
            log.info("Database queried")
            return scan_resp["Count"]
        except Exception as e:
            log.error(FetchUpdate.ERR_SCAN, str(e))
            raise e

    def send_resp(self, result: str, count: int, errorMsg: str) -> dict:
        """
        Step 4: Create the HTTP response object incl. any errors thrown in the process

        :param result: The result of the DB operation ("added"|"found"|""-default)
        :param count: The number of items found previously in the DB or -1 - default
        :param errorMsg: Error thrown previously or None - default

        :return: The HTTP response object, including the JSON body, that is immediately returned by the lambda handler.
                    THE JSON MUST BE PASSED THROUGH  ``json.dumps`` FIRST!!
        :rtype: dict
        """
        print("inside", result,count, errorMsg)
        jbody = {}

        if errorMsg:
            result = "error"
            jbody.update({"error": errorMsg})

        jbody.update({"result" : result})

        if count != -1: # visitor count might have been retrieved despite prev errors
            jbody.update({"visitors": count})
            code = 200
        else:
            code = 500

        resp = {
            'statusCode': code,
            "headers": {
                "Content-Type": "application/json"
            },
            'body': json.dumps(jbody,sort_keys=True)
        }
        print("returning", resp)
        return resp
