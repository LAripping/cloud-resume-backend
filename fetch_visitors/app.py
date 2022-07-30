import json
import boto3


def lambda_handler(event, context):
    """
    Processes client info (UA/IP) and adds them to the DB if they don't exist

    Paramters:
    event   : the JSON input
    context : ?

    Returns:
    JSON with params:
    result   : "added|found|error"
    visitors : N
    error    : (exception message if thrown)
    """

    # print(event["requestContext"])

    # Trying recursively (TODO deterministically)
    #  to get UA and IP, by just walking over
    #  all possible sources
    if ("requestContext" in event) \
            and ("http" in event["requestContext"]) \
            and ("sourceIp" in event["requestContext"]["http"]):
        ip = event["requestContext"]["http"]["sourceIp"]
    elif ("requestContext" in event) \
            and ("identity" in event["requestContext"]) \
            and ("sourceIp" in event["requestContext"]["identity"]):
        ip = event["requestContext"]["identity"]["sourceIp"]
    else:
        # TODO handle error
        pass

    if ("requestContext" in event) \
            and ("http" in event["requestContext"]) \
            and ("userAgent" in event["requestContext"]["http"]):
        ua = event["requestContext"]["http"]["userAgent"]
    elif ("requestContext" in event) \
            and ("identity" in event["requestContext"]) \
            and ("userAgent" in event["requestContext"]["identity"]):
        ua = event["requestContext"]["identity"]["userAgent"]
    else:
        # TODO handle error
        pass

    client = boto3.client('dynamodb')
    dynamodb = boto3.resource('dynamodb')

    # Step 1 : Try to add visitor to DB if not exists

    try:
        putitem_resp = client.put_item(
            TableName='VisitorsSam',    # TODO extract TBL_NAME constant
            Item={
                "UA": {"S": ua},
                "IP": {"S": ip}
            },
            ConditionExpression='attribute_not_exists(IP) and attribute_not_exists(UA)'
        )
        result = "added"
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        result = "found"

    # Step 2 : Query DB for visitor count

    scan_resp = client.scan(
        TableName='VisitorsSam',
        Select='COUNT',
        FilterExpression="test <> :istest",
        ExpressionAttributeValues={
            ":istest": {"BOOL": True}
        }
    )

    return {
        'statusCode': 200,
        "headers": {
            "Content-Type": "application/json"
        },
        'body': json.dumps({
            "result": result,
            "visitors": scan_resp["Count"]
        })
    }
