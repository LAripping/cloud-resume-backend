#!/bin/bash
ROLE_NAME=tf-lambda-role
CALLERID=$(aws sts get-caller-identity)
ACCOUNT_ID=$(echo "${CALLERID}" | jq -r .Account)
AWSUSER=$(echo "${CALLERID}" | jq -r .Arn | awk -F/ '{print $2}')
ROLE=$(aws sts assume-role \
          --role-arn "arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}" \
          --role-session-name "${AWSUSER}-session" --output json)
echo "AWS_ACCESS_KEY_ID=$(echo ${ROLE} | jq .Credentials.AccessKeyId | xargs)" >> $1 
echo "AWS_SECRET_ACCESS_KEY=$(echo ${ROLE} | jq .Credentials.SecretAccessKey | xargs)" >> $1 
echo "AWS_SESSION_TOKEN=$(echo ${ROLE} | jq .Credentials.SessionToken | xargs)" >> $1 