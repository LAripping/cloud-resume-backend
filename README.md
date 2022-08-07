# Cloud Resume Backend SAM stack 

The Infrastructure-as-Code (IaC) description of the AWS resources composing the backend of my [cloud resume application](https://resume.laripping.com).
All neatly described using [AWS Serverless Application Model (SAM)](https://aws.amazon.com/serverless/sam/), ready to deploy with just a few `sam` commands using the [SAM CLI](https://github.com/aws/aws-sam-cli) 

The SAM stack consists of:
- An API Gateway Rest API : that the frontend JS will interact with 
- A DynamoDB Table : holding visitors' User Agents and IP addresses
- A Python Lambda Function : serving as the controller that bridges the two

Extra goodies
- [ ] [Tests](#tests-written) (Integration & Unit)
- [ ] CI/CD pipelines (using Github Actions)

## Backend/Frontend Contract

- The backend API expects to be accessed with an **HTTP GET** request at the registered endpoint (`/Prod/fetch-update-visitor-count`)
- With no HTTP GET/POST parameters 
- (The actual parameters processed are the `User-Agent` HTTP request header and the client's source IP) 
- No authentication of any sort is required
- The API will respond with a "200 OK" status code if at least the count was retrieved, otherwise with a "500 Internal Server Error"
- When successful, the API will return a JSON with the following structure
    ```json
    {
        "result": "added|found|error",
        "visitors": <int>,
        ["error" : "Error message thrown despite count retrieval"]
    }
    ```
<hr/>


## Develop Locally
> 💡 Notes for me

- Download PyCharm and install the AWS IntelliJ Toolkit
- Git clone and Open the project into PyCharm
- Configure the AWS Toolkit with an IAM user (eg. `aws-toolkit`) and confirm you can access CloudWatch logs 
  1. From the sidebar, expand the AWS Toolkit window
  2. In the first dropdown, choose the `aws-toolkit` IAM profile you've just configured
  3. In the second dropdown pick `eu-west-2` region
  4. Refresh
  5. Under CloudWatch Logs, there should be an entry like `/aws/lambda/sam-app-... `



### SAM CLI prep

On first run, configure SAM cli as follows 
1. Create an IAM user for the SAM CLI (eg. `samcli`)
> 🔒 Follow Least Privilege Principle: the minimum set of permissions it needs to work most of the times is described [here](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-permissions.html#sam-permissions-managed-policies) 
2. Configure your AWS CLI with its creds (*as the default profile*) using `aws configure` 
> ❌ Unfortunately SAM CLI doesn't consistently follow `AWS_PROFILE` env, so we need have samcli be the default globally  
3. Extract the (fixed and rigid) stack name from conf, to use in commands
```bash
$ STACK_NAME=$(grep stack_name samconfig.toml | cut -d \" -f 2)
```
4. Set an alias to un-screw `os.getcwd()` after Docker-juggling (see the relevant [Troubleshooting](#troubleshooting) issue)
```bash
$ alias recd=cd ../ && cd -
```


### Python Setup 

To develop/test the Lambda function locally, using PyCharm in a WSL environment, you first need to setup the Python environment.  
We'll use a pyenv / pip / virtualenv combo:
```bash
$ cd hellow_world
$ pyenv virtualenv 3.8.0 .venv
$ pyenv activate .venv
$ python3 -m pip install -r requirements.txt
$ # do work, add imports... then update
$ python3 -m pip freeze > requirements.txt
```

Note that PyCharm won't work well with an interpreter inside WSL, so instead create another virtualenv interpreter for the project in Windows land, based off of Python(.exe) 3.8  with the `fetch_visitors/requirements.txt`. Name the virtualenv `venv` as to be ignored by git. Then finally `pip install -r requirements.txt` using that Windows-land `venv/python.exe` 



### AWS Resources

When messing with the `template.yaml` adding/removing AWS resources, follow the SAM cli workflow below:


```bash
$ sam build # --use-container takes way too long
$ # sam package <- use this to feed packaged.yaml to the next steps, if anything complains about the lack of S3 urls
$ sam deploy  
$ sam local invoke      # tests the function
$ sam local start-api   # tests the API + the function 
```

From now on, you can edit/test the Python code as described below, and see it live by hitting http://127.0.0.1:3000/fetch-update-visitor-count. 
- No need to rebuild/redeploy as changes will appear instantly (mounted docker env)
- Do rebuild if you change `template.yaml`

### Running Locally/Remotely

One-liners

- To test locally
```bash
$ recd && sam build && sam local invoke -e events/event-from-browser.json
# and see logs in your terminal
```

- To test remotely
```bash
$ recd && sam build && sam deploy
# then Hit in chrome
# ...and look at CloudWatch logs in PyCharm
```


### ~~Fetch, tail, and filter Lambda function logs~~
> ❌ This just doesn't work

To simplify troubleshooting, SAM CLI has a command called `sam logs`. `sam logs` lets you fetch logs generated by your deployed Lambda function from the command line. In addition to printing the logs on the terminal, this command has several nifty features to help you quickly find the bug.

`NOTE`: This command works for all AWS Lambda functions; not just the ones you deploy using SAM.

```bash
my-sam-tutorial-app$ sam logs -n HelloWorldFunction --stack-name my-sam-tutorial-app --tail
```

You can find more information and examples about filtering Lambda function logs in the [SAM CLI Documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-logging.html).



### Run Tests
> 🔑 Note that at least one integration test uses `boto3` client which needs to be configured with an IAM user allowed to 
> - `cloudformation:DescribeStacks:*`
> - `dynamodb:Scan:VisitorsSam`
> - `dynamodb:DynamoDeleteItem:VisitorsSam`
> Creds for this can be passed as environment variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

Tests are defined in the `tests` folder in this project and their `requirements.txt` are covered by the top-level ones. See [Tests Written](#tests-written) section for a listing.
To run test suites:
- from PyCharm: right-click the `tests` subdirectory and click "Run 'Python tests in test'..."
- in terminal: 

```bash
# Unit tests
$ python -m pytest tests/unit -v

# Integration tests (needs a deployment & $STACK_NAME to be set)
$ python -m pytest tests/integration -v
```

### All in one

If you've set the `AWS_` env vars for the `boto-test-runner` IAM user and want the SAM CLI commands to use your default -> `samcli` IAM user, run it all as such:
```bash
recd && sam build && sam deploy --profile default && python3 -m pytest tests/
```


### Troubleshooting 
- If you get weird Python SAM cli errors after `sam local invoke` maybe wait for a min / kill docker, it could be the mounted FS... or just `cd ../ && cd -`
- `sam deploy` complaining with "S3 Bucket not specified..." might be a silent permissions problem, as implicit assumption of an unintended profile forces the S3 call to fail misinterpretting it as an empty response. Make sure the right profile is picked up with `--debug`  

## Tests Written

### Integration tests

  > 🎯 Goal: To check that all components operate (integrate) with each other  
  > Testing multiple components at once  
  > "End 2 End"

  - [x] URL of API created responds to GET request as expected (200, json, valid result & count fields)
  - [x] Request takes less than 10 seconds to complete (= the timeout set server-side) to maintain performance when DB grows
  - [x] GET with time-based random UA results in addition (in JSON *and* by checking in the DB)

 

### Unit Tests

  > 🎯 Goal: To check a specific component  
  > Testing one single component at a time, to confirm that it operates in the right way. Helps you to isolate what is broken in your application and fix it faster  
  > "Per-Feature"

  - Step 0: Class instantiation
    - [ ] Boto Clients have been instantiated ok
  - Step 1: Extract IP & UA
    - [x] no `User-Agent` header is provided
  - Step 2: DB Put Item : faking `boto3.client('dynamodb').put_item()`to ... ->  ensure our `db_putitem()` ...
    - [x] return but not throw -> returns "added"
    - [x] throw the "ConditionalCheckFailedException" -> returns "found"
    - [x] throw any other "ClientError" -> throws as well
    - [x] throw any other Exception -> throws as well
  - Step 3: DB Scan : faking `boto3.client('dynamodb).scan()` to ... -> ensure our `db_scan()` ...
    - [x] returns a legit count -> returns that number
    - [x] throws -> we throw too
    - [x] returns a resp with no "Count" key -> : this is intended to catch any upstream changes in boto3 that would break our app. Atm we won't handle it so we expect it to fail
  - Step 4: 

### Design Decisions
Documenting the "why"s regarding the organisation and implementation of test code 

1.`pytest` instead of `unittest`, mainly due to [this](https://www.slant.co/versus/9148/9149/~unittest_vs_pytest)
  - so we'll use `@fixtures` instead of `self.setUp`
  - for fixtures involving events we'll extract into files to allow re-use 
  - we're allowed to have some stray `test_*` methods in `.py` files, instead of class-methods only
  - we'll simply name test case classes `Test*`, we won't subclass `unittest.TestCase`
2. We'll use end-2-end tests as Integration ones, conscious it's not the same (as per the [pyramid](https://blogs.sap.com/2022/02/16/how-to-write-independent-unit-test-with-pytest-and-mock-techniques/))
3. [Integration] One `test*.py` file > One `class Test*` per feature > One `def test_*` method per case...
4. [Unit] One `test*.py` file per ~~src file~~ ~~src class~~ feature (so add a new one when the profiling comes in) > One `class Test*` per Step > One `def test_*`per case
5. simple `assert expr` without messages, to make use of pytest's Advanced Assertion Introspection (AAI). Not unittest's redundant `self.assertSomething`  
6. Annotate with `#Arrange -> #Act -> #Assert`

==TODO== Insert pic here of the PyCharm test output window highlighting the organisation