#!/bin/bash
set -e

export AWS_PROFILE=personal
export AWS_REGION=eu-west-3

echo "🚀 Deploying Flibusta Telegram Bot with AWS CDK (Python)..."

# Check if bot token is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <BOT_TOKEN>"
    echo "Example: $0 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    exit 1
fi

BOT_TOKEN="$1"

echo "📋 Configuration:"
echo "   Bot Token: ${BOT_TOKEN:0:10}..."

# Activate virtual environment
echo "🐍 Activating Python virtual environment..."
source .venv/bin/activate || {
    echo "❌ Virtual environment not found. Please run 'python -m venv .venv' first."
    exit 1
}

# Install Python CDK dependencies
echo "📦 Installing CDK dependencies..."
pip install -r requirements.txt

# Install Python dependencies for Lambda in the lambda directory
echo "📦 Installing Lambda dependencies..."
cd lambda
pip install -r requirements.txt -t .
cd ..

# Bootstrap CDK (if not already done)
# Don't run bootstrap, it's already done.
#echo "🔧 Bootstrapping CDK..."
#cdk bootstrap --require-approval never || echo "CDK already bootstrapped"

# Check if stack exists and is in a failed state, then destroy it
echo "🧹 Checking for failed stack..."
STACK_STATUS=$(aws cloudformation describe-stacks --stack-name FlibustaBotStack --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")
if [[ "$STACK_STATUS" == "ROLLBACK_FAILED" || "$STACK_STATUS" == "CREATE_FAILED" || "$STACK_STATUS" == "DELETE_FAILED" ]]; then
    echo "⚠️  Found failed stack in status: $STACK_STATUS"
    echo "🗑️  Destroying failed stack..."
    cdk destroy FlibustaBotStack --force || true
    echo "⏳ Waiting for stack deletion to complete..."
    aws cloudformation wait stack-delete-complete --stack-name FlibustaBotStack || true
fi

# Deploy the stack
echo "☁️  Deploying stack..."
cdk deploy FlibustaBotStack --require-approval never --parameters BotToken="$BOT_TOKEN"

echo ""
echo "✅ Deployment completed!"
echo ""
echo "📊 Check the stack outputs for:"
echo "   • Lambda Function URL (for accessing files)"
echo "   • S3 Bucket name"
echo "   • Usage instructions"
echo ""
echo "🎉 Your Telegram bot is ready!"
echo "   1. Find your bot on Telegram and send /start"
echo "   2. Upload EPUB/PDF files or send direct URLs"
echo "   3. Access your files via the Function URL"
echo ""
