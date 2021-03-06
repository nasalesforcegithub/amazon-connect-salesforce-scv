import sys
from pip._internal import main

main(['install', 'boto3', '--target', '/tmp/'])
main(['install', 'requests', '--target', '/tmp/'])
sys.path.insert(0,'/tmp/')

import json
import boto3
import os
import logging
import requests
import urllib3
http = urllib3.PoolManager()
flowPath = os.environ['LAMBDA_TASK_ROOT'] + '/awsscv_ddr_flow_cf.json'

def lambda_handler(event, context):

    print(event)

    # Create response container
    response = {'result':'success'}

    # Deal with deletes
    if event['RequestType'] == 'Delete':
        cf_send(event, context, 'SUCCESS', {})
        response.update({'event':'CF Delete'})
        return response

    # Setup the template
    try:
        # Grab ARNs from CF Template
        flow_arn = event['ResourceProperties']['flow_arn']
        processor_arn = event['ResourceProperties']['processor_arn']
        telephony_arn = event['ResourceProperties']['telephony_arn']
        queue_arn = event['ResourceProperties']['queue_arn']

        # Open the template and extract the flow
        flow_file = open(flowPath).read()
        flow_template_raw = json.loads(flow_file)
        starting_content = flow_template_raw['ContactFlow']['Content']

        # Swap the Function ARNs
        new_content = starting_content.replace('REPLACEDDRFLOW',flow_arn)
        new_content = new_content.replace('REPLACETARGET',processor_arn)
        new_content = new_content.replace('REPLACETELEPHONY',telephony_arn)
        new_content = new_content.replace('REPLACEQUEUE',queue_arn)

        print('We have the template and modifications were successful')
        response.update({'template_setup':'complete'})

    except:
        print('failed to get file and parse')
        cf_send(event, context, 'FAILED', {})
        response.update({'template_setup':'failed'})
        response.update({'result':'fail'})
        return response

    # Create the flow in the instance
    try:
        connect_client = boto3.client('connect')

        make_flow = connect_client.create_contact_flow(
            InstanceId=os.environ['instanceID'],
            Name=event['ResourceProperties']['flow_name'],
            Type='CONTACT_FLOW',
            Description='Example flow generated by Cloudformation',
            Content=new_content
        )

        cf_send(event, context, 'SUCCESS', {})
        response.update({'flow_build':'complete'})

    except:
        print('failed to create contact flow')
        cf_send(event, context, 'FAILED', {})
        response.update({'flow_build':'failed'})
        response.update({'result':'fail'})
        return response

    return response

def cf_send(event, context, responseStatus, responseData, physicalResourceId=None, noEcho=False):
    responseUrl = event['ResponseURL']

    print(responseUrl)

    responseBody = {}
    responseBody['Status'] = responseStatus
    responseBody['Reason'] = 'See the details in CloudWatch Log Stream: ' + context.log_stream_name
    responseBody['PhysicalResourceId'] = physicalResourceId or context.log_stream_name
    responseBody['StackId'] = event['StackId']
    responseBody['RequestId'] = event['RequestId']
    responseBody['LogicalResourceId'] = event['LogicalResourceId']
    responseBody['NoEcho'] = noEcho
    responseBody['Data'] = responseData

    json_responseBody = json.dumps(responseBody)

    print("Response body:\n" + json_responseBody)

    headers = {
        'content-type' : '',
        'content-length' : str(len(json_responseBody))
    }

    try:

        response = http.request('PUT',responseUrl,body=json_responseBody.encode('utf-8'),headers=headers)
        print("Status code: " + response.reason)

    except Exception as e:
        print("send(..) failed executing requests.put(..): " + str(e))
