
# Flibusta Telegram Bot - AWS CDK Implementation

A serverless Telegram bot that manages file uploads and provides a public file listing interface using AWS CDK (Python).

## Features

The Lambda function serves three roles:
1. **Self-registration**: Automatically registers webhook with Telegram API on deployment
2. **Telegram bot**: Receives files and URLs from users, stores them in S3
3. **File listing**: Serves a public HTML page with downloadable file links (no authentication required)

### Dual Access Modes

**🌐 S3 Static Website** (NEW!)
- Public S3 website hosting with direct file access
- No expiring URLs - files accessible via relative paths
- Automatically regenerated `index.html` after each upload
- Fast, cached, and cost-effective

**⚡ Lambda Function URL** (Dynamic)
- Dynamic HTML generation with presigned URLs
- Real-time file listing
- Expires after 1 hour for security

## Architecture

- **AWS Lambda**: Single function handling all three roles (Python 3.9)
- **S3 Bucket**: Secure file storage with encryption, lifecycle management, and static website hosting
- **S3 Static Website**: Public website with direct file access and auto-generated index
- **Lambda Function URL**: Direct HTTP access without API Gateway
- **Custom Resource**: Automatic webhook registration during CDK deployment

## Prerequisites

1. **AWS CLI configured** with appropriate credentials
2. **AWS CDK CLI installed**: `npm install -g aws-cdk`
3. **Python 3.9+** with virtual environment support
4. **Telegram Bot Token** from [@BotFather](https://t.me/BotFather)

## Setup & Deployment

### 1. Clone and Setup
```bash
git clone <repository-url>
cd bookatalog

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Deploy
```bash
# Make deployment script executable
chmod +x deploy-cdk.sh

# Deploy with your bot token
./deploy-cdk.sh YOUR_BOT_TOKEN_HERE
```

Example:
```bash
./deploy-cdk.sh 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
```

### 3. Usage

After successful deployment:

1. **Find your bot** on Telegram and send `/start`
2. **Upload files**: Send EPUB, PDF, or other document files
3. **Send URLs**: Send direct download links to files
4. **Access files**: 
   - **S3 Static Website**: Visit the S3 website URL for permanent, direct file access
   - **Lambda Function URL**: Visit the Lambda URL for dynamic, presigned file access

## Project Structure

```
bookatalog/
├── app.py                    # CDK app entry point
├── bookatalog/
│   └── bookatalog_stack.py   # Main CDK stack definition
├── lambda/
│   ├── lambda_function.py    # Lambda function code (3 roles)
│   └── requirements.txt      # Lambda dependencies
├── deploy-cdk.sh             # Automated deployment script
├── requirements.txt          # CDK dependencies
└── cdk.json                 # CDK configuration
```

## CDK Commands

```bash
# Synthesize CloudFormation template
cdk synth

# Deploy the stack
cdk deploy FlibustaBotStack --parameters BotToken=YOUR_TOKEN

# Destroy the stack
cdk destroy FlibustaBotStack
```

## Security Features

- S3 bucket with encryption and restricted public access
- IAM roles with least-privilege permissions
- No authentication required for file listing (by design)
- Secure bot token handling through CloudFormation parameters

## Customization

- Modify `lambda/lambda_function.py` to change bot behavior
- Update `bookatalog/bookatalog_stack.py` to adjust AWS resources
- Customize file storage and lifecycle policies in the S3 bucket configuration
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdk synth
```

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!
