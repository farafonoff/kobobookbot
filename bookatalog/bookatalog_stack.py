from aws_cdk import (
    Duration,
    Stack,
    CfnParameter,
    CfnOutput,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_iam as iam,
    custom_resources as cr,
)
from constructs import Construct
import os
import json

class BookatalogStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Bot token parameter
        bot_token = CfnParameter(
            self, "BotToken",
            type="String",
            description="Telegram Bot Token from @BotFather",
            no_echo=True
        )

        # S3 bucket for file storage with static website hosting
        files_bucket = s3.Bucket(
            self, "FilesBucket",
            bucket_name=f"flibusta-books-{self.account}-{self.region}",
            # Enable public access for static website hosting
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False
            ),
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            # Enable static website hosting
            website_index_document="index.html",
            website_error_document="error.html",
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    enabled=True,
                    noncurrent_version_expiration=Duration.days(30)
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # Add bucket policy for public read access to static website
        files_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="PublicReadGetObject",
                effect=iam.Effect.ALLOW,
                principals=[iam.AnyPrincipal()],
                actions=["s3:GetObject"],
                resources=[f"{files_bucket.bucket_arn}/*"]
            )
        )

        # Lambda function for the bot
        bot_function = _lambda.Function(
            self, "BotFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "../lambda")
            ),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "BOT_TOKEN": bot_token.value_as_string,
                "BUCKET_NAME": files_bucket.bucket_name
            }
        )

        # Grant S3 permissions to Lambda
        files_bucket.grant_read_write(bot_function)

        # Lambda Function URL for HTTP access (no API Gateway)
        function_url = bot_function.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,
            cors=_lambda.FunctionUrlCorsOptions(
                allowed_origins=["*"],
                allowed_methods=[_lambda.HttpMethod.GET, _lambda.HttpMethod.POST],
                allowed_headers=["*"]
            )
        )

        # Custom resource to register Telegram webhook on deployment
        webhook_registration = cr.AwsCustomResource(
            self, "WebhookRegistration",
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": bot_function.function_name,
                    "Payload": json.dumps({
                        "RequestType": "Create",
                        "ServiceToken": bot_function.function_arn,
                        "WebhookUrl": function_url.url
                    })
                },
                physical_resource_id=cr.PhysicalResourceId.of("telegram-webhook-registration")
            ),
            on_update=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": bot_function.function_name,
                    "Payload": json.dumps({
                        "RequestType": "Update",
                        "ServiceToken": bot_function.function_arn,
                        "WebhookUrl": function_url.url
                    })
                },
                physical_resource_id=cr.PhysicalResourceId.of("telegram-webhook-registration")
            ),
            on_delete=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": bot_function.function_name,
                    "Payload": json.dumps({
                        "RequestType": "Delete",
                        "ServiceToken": bot_function.function_arn
                    })
                }
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["lambda:InvokeFunction"],
                    resources=[bot_function.function_arn]
                )
            ])
        )

        # Ensure webhook registration happens after function URL is created
        webhook_registration.node.add_dependency(function_url)

        # Outputs
        CfnOutput(
            self, "LambdaFunctionUrl",
            value=function_url.url,
            description="Lambda Function URL for bot and file access"
        )

        CfnOutput(
            self, "S3BucketName", 
            value=files_bucket.bucket_name,
            description="S3 bucket name for file storage"
        )

        CfnOutput(
            self, "S3StaticWebsiteUrl",
            value=files_bucket.bucket_website_url,
            description="S3 static website URL (public access, relative links)"
        )

        CfnOutput(
            self, "TelegramWebhookUrl",
            value=function_url.url,
            description="URL registered as Telegram webhook"
        )

        CfnOutput(
            self, "DeploymentInstructions",
            value=f"Lambda URL (dynamic): {function_url.url} | S3 Website (static): {files_bucket.bucket_website_url}",
            description="Access files via Lambda (presigned URLs) or S3 static website (direct links)"
        )
