import json
import boto3
import logging
import os
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
    origin = ""
    try:
        ip, ua = fu.extract_ip_ua()
        origin = fu.extract_origin()
        result = fu.db_putitem(ip, ua)
        count = fu.db_scan()
    except Exception as e:
        errorMsg = str(e)
    finally:
        return fu.send_resp(result, count, errorMsg, origin)


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
    ERR_NO_ENV = "Environment variable %s required not found!"
    ERR_NO_ORIGIN = "Couldn't extract Origin!"
    ERR_PUT_ITEM = "Unexpected error while putting item: %s"
    ERR_SCAN = "Unexpected error while scanning DB: %s"
    TABLE_NAME = ""  # set by the env var API_URL on __init__()
    DEFAULT_ACAO = ""   # set by the env var API_URL on __init__()
    ORIGIN_WHITELIST = [
        DEFAULT_ACAO,
        "http://localhost:5555",
        "http://127.0.0.1:5555",
        "http://127.0.0.1:8000",
    ]

    def __init__(self, event):
        self.event = event
        self.client = boto3.client('dynamodb', region_name='eu-west-2')
        self.dynamodb = boto3.resource('dynamodb', region_name='eu-west-2')  # needed for the exception
        try:
            self.DEFAULT_ACAO = os.environ["API_URL"]
            self.TABLE_NAME = os.environ["TABLE_NAME"]
        except KeyError as e:
            log.error(FetchUpdate.ERR_NO_ENV, str(e.args[0]))
            raise Exception(FetchUpdate.ERR_NO_ENV)
        log.info("Init'ed FetchUpdate - API URL: %s", self.DEFAULT_ACAO)

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

    def extract_origin(self) -> str:
        """
        TODO untested!
        Step 1.5: Try to get the requestor's Origin to process our ACAO response in Step 4 below
        If no Origin is found, we just return the empty string and in Step 4 we include no ACAO

        :return: the client's Origin domain
        :raises: Exception when Origin can't be found
        """

        if ("headers" in self.event) \
                and ("origin" in self.event["headers"]):
            origin = self.event["headers"]["origin"]
        elif ("headers" in self.event) \
                and ("Origin" in self.event["headers"]):
            origin = self.event["headers"]["Origin"]
        else:
            return ""

        log.info("Successfully extracted Origin %s", origin)
        return origin

    def db_putitem(self, ip, ua) -> str:
        """
        Step 2: Try to add visitor info to DB if not exists

        :return: The result of the database insertion (added|found) OR throws
        :rtype: str
        :raises: Exception when PutItem operation fails
        """

        try:
            putitem_resp = self.client.put_item(
                TableName=self.TABLE_NAME,
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
                TableName=self.TABLE_NAME,
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

    def send_resp(self, result: str, count: int, errorMsg: str, origin: str) -> dict:
        """
        Step 4: Create the HTTP response object incl. any errors thrown in the process

        :param result: The result of the DB operation ("added"|"found"|""-default)
        :param count: The number of items found previously in the DB or -1 - default
        :param errorMsg: Error thrown previously or None - default
        :param origin: Request origin to process response ACAO header OR ""

        :return: The HTTP response object, including the JSON body, that is immediately returned by the lambda handler.
                    THE JSON MUST BE PASSED THROUGH  ``json.dumps`` FIRST!!
        :rtype: dict
        """
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

        headers = { "Content-Type": "application/json"}
        # If there's an Origin header, IFF it's an allowed one,  mirror it back into the ACAO header
        # https://stackoverflow.com/questions/1653308/access-control-allow-origin-multiple-origin-domains
        if origin:
            acao = self.DEFAULT_ACAO
            if origin in self.ORIGIN_WHITELIST:
                acao = origin
            headers.update({"Access-Control-Allow-Origin": acao})

        resp = {
            'statusCode': code,
            "headers": headers,
            'body': json.dumps(jbody,sort_keys=True)
        }
        return resp
