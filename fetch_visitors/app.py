import json
import boto3
import logging
log = logging.getLogger()
log.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Processes client info (UA/IP) and adds them to the DB if they don't exist

    Parameters:
        event (dict): the JSON input
        context (dict): ?

    Returns:
        dict: A JSON with keys
            result (str): "added|found|error"
            visitors (int): N
            error (str): Stringified exception message if thrown
    """

    result = ""
    errorMsg = None
    fu = FetchUpdate(event)
    try:
        ip,ua = fu.extract_ip_ua()
        result = fu.db_putitem(ip, ua)
    except Exception as e:
        errorMsg = str(e)
    finally:
        count = fu.db_scan()
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

    def __init__(self, event):
        self.event = event
        self.client = boto3.client('dynamodb')
        self.dynamodb = boto3.resource('dynamodb')

    def extract_ip_ua(self) -> tuple:
        """
        Step 1: Try recursively (TODO deterministically)
        to get the the requestor's source IPv4 address and User-Agent, by just walking over
        all the places these could be found in
        :return: (ip,ua) a 2-tuple of strings if found
        :rtype: tuple
        :raises: Exception when IP/UA can't be found
        """
        log.info("Event object passed:\n%s", self.event)

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

        log.info("Successfully extracted IP (%s) and UA (%s)", ip,ua)
        return ip, ua

    def db_putitem(self, ip, ua) -> str:
        """
        Step 2: Try to add visitor info to DB if not exists

        :return: The result of the database insertion (added|found|error)
        :rtype: str
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
            log.info("Visitor details added to the database")
            result = "added"
        except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            log.info("Visitor details already in the database. Not added")
            result = "found"
        return result

    def db_scan(self) -> int:
        """
        Step 3: Query DB for the number of total visitors seen

        :return: The number of items found in the DB
        :rtype: int
        """

        scan_resp = self.client.scan(
            TableName='VisitorsSam',
            Select='COUNT',
            FilterExpression="test <> :istest",
            ExpressionAttributeValues={
                ":istest": {"BOOL": True}
            }
        )
        return scan_resp["Count"]

    def send_resp(self, result, count, errorMsg: str) -> dict:
        """
        Step 4: Create the HTTP response object incl. any errors thrown in the process

        :param result: The result of the DB operation (added|found|error)
        :param count: The number of items found previously in the DB
        :return: The HTTP response object, including the JSON body, that is immediately returned by the lambda handler
        :rtype: dict
        """

        jbody = {
                "result": "error" if errorMsg else result,
                "visitors": count
        }
        if errorMsg:
            jbody.update( {"error":errorMsg} )


        return {
            'statusCode': 200,
            "headers": {
                "Content-Type": "application/json"
            },
            'body': json.dumps(jbody)
        }




