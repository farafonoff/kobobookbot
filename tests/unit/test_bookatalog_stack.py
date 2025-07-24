import aws_cdk as core
import aws_cdk.assertions as assertions

from bookatalog.bookatalog_stack import BookatalogStack

# example tests. To run these tests, uncomment this file along with the example
# resource in bookatalog/bookatalog_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = BookatalogStack(app, "bookatalog")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
