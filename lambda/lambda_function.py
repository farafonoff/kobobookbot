import json
import boto3
import os
import requests
import logging
import urllib.parse
from datetime import datetime
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
BOT_TOKEN = os.environ['BOT_TOKEN']
BUCKET_NAME = os.environ['BUCKET_NAME']
AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-3')  # AWS Lambda automatically provides this

# Initialize AWS clients with explicit region
s3_client = boto3.client('s3', region_name=AWS_REGION, endpoint_url='https://s3.' + AWS_REGION + '.amazonaws.com')

def lambda_handler(event, context):
    """Main Lambda handler - handles 3 roles:
    1. Webhook registration (custom resource)
    2. Telegram bot webhook
    3. File listing HTTP endpoint
    """
    try:
        logger.info(f"Received event: {json.dumps(event, default=str)}")
        
        # Role 1: Handle CDK custom resource for webhook registration
        if 'RequestType' in event and 'ServiceToken' in event:
            return handle_webhook_registration(event, context)
        
        # Role 2 & 3: Handle HTTP requests from Lambda Function URL
        request_context = event.get('requestContext', {})
        http_method = request_context.get('http', {}).get('method', '')
        
        if http_method == 'POST':
            # Role 2: Handle Telegram webhook
            return handle_telegram_webhook(event, context)
        elif http_method == 'GET':
            # Role 3: Serve file listing HTML page
            return handle_file_listing(event, context)
        else:
            return {
                'statusCode': 405,
                'body': json.dumps({'error': 'Method not allowed'})
            }
            
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }

def handle_webhook_registration(event, context):
    """Role 1: Handle webhook registration during CDK deployment"""
    try:
        request_type = event['RequestType']
        webhook_url = event.get('WebhookUrl', '')
        
        logger.info(f"Webhook registration request: {request_type}")
        
        if request_type in ['Create', 'Update']:
            # Set up Telegram webhook
            result = set_telegram_webhook(webhook_url)
            
            # Initialize static website on first deployment
            if request_type == 'Create':
                try:
                    regenerate_static_index()
                    logger.info("Initial static website created")
                except Exception as e:
                    logger.error(f"Failed to create initial static website: {str(e)}")
                    # Don't fail deployment if static website creation fails
            
            if result['success']:
                logger.info(f"Webhook registered successfully: {webhook_url}")
                return {
                    'Status': 'SUCCESS',
                    'Data': {
                        'Message': 'Webhook registered successfully',
                        'WebhookUrl': webhook_url
                    }
                }
            else:
                logger.error(f"Failed to register webhook: {result['error']}")
                return {
                    'Status': 'FAILED',
                    'Reason': result['error']
                }
        elif request_type == 'Delete':
            result = remove_telegram_webhook()
            logger.info("Webhook deletion completed")
            return {
                'Status': 'SUCCESS',
                'Data': {'Message': 'Webhook removed'}
            }
        
    except Exception as e:
        logger.error(f"Error in webhook registration: {str(e)}")
        return {
            'Status': 'FAILED',
            'Reason': str(e)
        }

def handle_telegram_webhook(event, context):
    """Role 2: Handle incoming Telegram messages"""
    try:
        body = json.loads(event['body'])
        
        if 'message' not in body:
            return {'statusCode': 200, 'body': 'OK'}
            
        message = body['message']
        chat_id = message['chat']['id']
        
        # Handle different message types
        if 'document' in message:
            handle_file_upload(message, chat_id)
        elif 'text' in message:
            handle_text_message(message, chat_id)
        else:
            send_telegram_message(chat_id, "Send EPUB/PDF files or direct file URLs")
        
        return {'statusCode': 200, 'body': 'OK'}
        
    except Exception as e:
        logger.error(f"Error in telegram webhook: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

def handle_file_listing(event, context):
    """Role 3: Serve HTML page with file list"""
    try:
        files = get_recent_files_from_s3()
        html_content = generate_html_page(files)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'text/html; charset=utf-8',
                'Cache-Control': 'no-cache'
            },
            'body': html_content
        }
        
    except Exception as e:
        logger.error(f"Error serving file list: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/html'},
            'body': f'<html><body><h1>Error</h1><p>{str(e)}</p></body></html>'
        }

def handle_file_upload(message, chat_id):
    """Handle file uploads from Telegram"""
    try:
        document = message['document']
        file_name = document.get('file_name', 'unknown_file')
        file_size = document.get('file_size', 0)
        
        # Validate file
        if file_size > 20 * 1024 * 1024:  # 20MB limit
            send_telegram_message(chat_id, "❌ File too large (max 20MB)")
            return
        
        if not file_name.lower().endswith(('.epub', '.pdf')):
            send_telegram_message(chat_id, "❌ Only EPUB and PDF files allowed")
            return
        
        # Download and store
        file_content = download_telegram_file(document['file_id'])
        if file_content:
            s3_key = f"files/{datetime.now().strftime('%Y/%m/%d')}/{file_name}"
            upload_to_s3(file_content, s3_key, file_name)
            send_telegram_message(chat_id, f"✅ File '{file_name}' uploaded successfully!")
        else:
            send_telegram_message(chat_id, "❌ Failed to download file")
            
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        send_telegram_message(chat_id, f"❌ Error: {str(e)}")

def handle_text_message(message, chat_id):
    """Handle text messages (commands and URLs)"""
    try:
        text = message['text'].strip()
        
        if text == '/start':
            welcome_msg = """🤖 **Flibusta File Manager Bot**

📚 **What I can do:**
• Upload EPUB/PDF files directly
• Download files from URLs
• Store files in secure cloud storage

📎 **How to use:**
• Send me an EPUB or PDF file
• Send me a direct file URL (e.g., http://example.com/book.epub)
• Use `/regenerate` to update the static website

🌐 **Access your files:** Check the deployment outputs for the web URL"""
            
            send_telegram_message(chat_id, welcome_msg)
            
        elif text == '/regenerate':
            handle_regenerate_command(chat_id)
            
        elif text == '/help':
            help_msg = """🤖 **Available Commands:**

📋 **Basic Commands:**
• `/start` - Welcome message and instructions
• `/help` - Show this help message
• `/regenerate` - Manually update static website

📁 **File Management:**
• Send EPUB/PDF files directly
• Send direct download URLs (must end with .epub or .pdf)

🌐 **Access Methods:**
• **S3 Static Website** - Permanent direct links
• **Lambda Function URL** - Dynamic presigned links

💡 **Tips:**
• Files up to 20MB are supported
• Website updates automatically on upload
• Use `/regenerate` if website seems outdated"""
            
            send_telegram_message(chat_id, help_msg)
            
        elif text.startswith(('http://', 'https://')):
            handle_url_download(text, chat_id)
        else:
            send_telegram_message(chat_id, "Send `/help` for commands, upload a file, or send a direct file URL")
            
    except Exception as e:
        logger.error(f"Error handling text message: {str(e)}")
        send_telegram_message(chat_id, f"❌ Error: {str(e)}")

def handle_url_download(url, chat_id):
    """Download file from URL"""
    try:
        if not url.lower().endswith(('.epub', '.pdf')):
            send_telegram_message(chat_id, "❌ URL must point to an EPUB or PDF file")
            return
        
        send_telegram_message(chat_id, f"⬇️ Downloading from URL...")
        
        # Download file
        response = requests.get(url, timeout=25, stream=True)
        response.raise_for_status()
        
        # Check size
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > 20 * 1024 * 1024:
            send_telegram_message(chat_id, "❌ File too large (max 20MB)")
            return
        
        # Extract filename
        parsed_url = urllib.parse.urlparse(url)
        file_name = os.path.basename(parsed_url.path) or f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # Store file
        file_content = response.content
        s3_key = f"files/{datetime.now().strftime('%Y/%m/%d')}/{file_name}"
        upload_to_s3(file_content, s3_key, file_name)
        
        send_telegram_message(chat_id, f"✅ File '{file_name}' downloaded and saved!")
        
    except Exception as e:
        logger.error(f"Error downloading URL: {str(e)}")
        send_telegram_message(chat_id, f"❌ Download failed: {str(e)}")

def handle_regenerate_command(chat_id):
    """Handle /regenerate command to manually update static website"""
    try:
        send_telegram_message(chat_id, "🔄 Regenerating static website...")
        
        # Regenerate the static index
        files = get_files_for_static_html()
        regenerate_static_index()
        
        # Get deployment outputs info
        website_info = f"""✅ **Static website regenerated!**

📊 **Statistics:**
• Files indexed: {len(files)}
• Total size: {sum(f['size'] for f in files) / (1024*1024):.1f} MB

🌐 **Access your files:**
• S3 Static Website: Check deployment outputs
• Lambda Function URL: Check deployment outputs

💡 The static website is updated automatically when you upload files, but you can use `/regenerate` anytime to refresh it manually."""
        
        send_telegram_message(chat_id, website_info)
        
    except Exception as e:
        logger.error(f"Error in regenerate command: {str(e)}")
        send_telegram_message(chat_id, f"❌ Failed to regenerate: {str(e)}")

def download_telegram_file(file_id):
    """Download file from Telegram servers"""
    try:
        # Get file info
        file_info_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(file_info_url, timeout=10)
        response.raise_for_status()
        
        file_info = response.json()
        if not file_info['ok']:
            raise Exception(f"Telegram API error: {file_info}")
        
        file_path = file_info['result']['file_path']
        
        # Download file
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        response = requests.get(download_url, timeout=25)
        response.raise_for_status()
        
        return response.content
        
    except Exception as e:
        logger.error(f"Error downloading from Telegram: {str(e)}")
        return None

def upload_to_s3(file_content, s3_key, original_filename):
    """Upload file to S3 and regenerate static index.html"""
    try:
        content_type = 'application/epub+zip' if original_filename.lower().endswith('.epub') else 'application/pdf'
        
        # Upload the file
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=file_content,
            ContentType=content_type,
            Metadata={
                'original-filename': original_filename,
                'upload-timestamp': datetime.now().isoformat()
            }
        )
        
        logger.info(f"File uploaded to S3: {s3_key}")
        
        # Regenerate static index.html after successful upload
        try:
            regenerate_static_index()
            logger.info("Static index.html regenerated successfully")
        except Exception as e:
            logger.error(f"Failed to regenerate static index: {str(e)}")
            # Don't fail the upload if index regeneration fails
        
    except ClientError as e:
        logger.error(f"S3 upload error: {str(e)}")
        raise

def send_telegram_message(chat_id, text):
    """Send message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
    except Exception as e:
        logger.error(f"Error sending Telegram message: {str(e)}")

def set_telegram_webhook(webhook_url):
    """Set Telegram webhook"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        payload = {'url': webhook_url}
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        return {
            'success': result.get('ok', False),
            'error': result.get('description', 'Unknown error') if not result.get('ok') else None
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def remove_telegram_webhook():
    """Remove Telegram webhook"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        return {'success': result.get('ok', False)}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_recent_files_from_s3(limit=20):
    """Get recent files from S3 (dynamic version with presigned URLs)"""
    try:
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix='files/',
            MaxKeys=1000
        )
        
        files = []
        if 'Contents' in response:
            sorted_objects = sorted(
                response['Contents'],
                key=lambda x: x['LastModified'],
                reverse=True
            )
            
            for obj in sorted_objects[:limit]:
                presigned_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': BUCKET_NAME, 'Key': obj['Key']},
                    ExpiresIn=3600
                )
                
                filename = os.path.basename(obj['Key'])
                files.append({
                    'filename': filename,
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'download_url': presigned_url
                })
        
        return files
        
    except ClientError as e:
        logger.error(f"Error listing S3 objects: {str(e)}")
        return []

def get_files_for_static_html(limit=50):
    """Get recent files from S3 for static website (with S3 keys, no presigned URLs)"""
    try:
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix='files/',
            MaxKeys=1000
        )
        
        files = []
        if 'Contents' in response:
            sorted_objects = sorted(
                response['Contents'],
                key=lambda x: x['LastModified'],
                reverse=True
            )
            
            for obj in sorted_objects[:limit]:
                filename = os.path.basename(obj['Key'])
                files.append({
                    'filename': filename,
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    's3_key': obj['Key']  # Relative path for static website
                })
        
        return files
        
    except ClientError as e:
        logger.error(f"Error listing S3 objects for static HTML: {str(e)}")
        return []

def regenerate_static_index():
    """Regenerate and upload index.html to S3 root for static website"""
    try:
        # Get files for static HTML (with S3 keys)
        files = get_files_for_static_html()
        
        # Generate static HTML
        html_content = generate_static_html_page(files)
        
        # Upload to S3 root as index.html
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key='index.html',
            Body=html_content.encode('utf-8'),
            ContentType='text/html; charset=utf-8',
            CacheControl='max-age=300',  # 5 minute cache
            Metadata={
                'generated-at': datetime.now().isoformat(),
                'file-count': str(len(files))
            }
        )
        
        logger.info(f"Static index.html regenerated with {len(files)} files")
        
        # Also create/update error.html for static website
        create_error_html()
        
    except ClientError as e:
        logger.error(f"Error regenerating static index: {str(e)}")
        raise

def create_error_html():
    """Create error.html for S3 static website"""
    try:
        error_html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>📚 File Not Found - Flibusta</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .container {
                    max-width: 500px;
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                    padding: 40px;
                    text-align: center;
                }
                h1 {
                    color: #2196F3;
                    font-size: 3em;
                    margin: 0 0 20px 0;
                }
                p {
                    color: #666;
                    font-size: 1.2em;
                    margin-bottom: 30px;
                }
                .btn {
                    display: inline-block;
                    background: #2196F3;
                    color: white;
                    padding: 12px 24px;
                    border-radius: 6px;
                    text-decoration: none;
                    transition: background 0.3s;
                }
                .btn:hover {
                    background: #1976D2;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📚</h1>
                <h2>File Not Found</h2>
                <p>The file you're looking for doesn't exist or has been moved.</p>
                <a href="/" class="btn">← Back to File Library</a>
            </div>
        </body>
        </html>
        """
        
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key='error.html',
            Body=error_html.encode('utf-8'),
            ContentType='text/html; charset=utf-8',
            CacheControl='max-age=3600'  # 1 hour cache for error page
        )
        
        logger.info("Error page created/updated")
        
    except ClientError as e:
        logger.error(f"Error creating error.html: {str(e)}")

def generate_file_rows(files, use_static_links=False):
    """Generate HTML table rows for files"""
    if not files:
        return '<tr><td colspan="3" style="text-align: center; color: #666;">No files uploaded yet</td></tr>'
    
    file_rows = ""
    for file_info in files:
        size_mb = file_info['size'] / (1024 * 1024)
        size_str = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{file_info['size'] / 1024:.1f} KB"
        date_str = file_info['last_modified'].strftime('%Y-%m-%d %H:%M')
        
        # Use either static relative path or presigned URL
        file_url = file_info['s3_key'] if use_static_links else file_info['download_url']
        
        file_rows += f"""
        <tr>
            <td><a href="{file_url}" download="{file_info['filename']}">{file_info['filename']}</a></td>
            <td>{size_str}</td>
            <td>{date_str}</td>
        </tr>
        """
    
    return file_rows

def get_html_css():
    """Get shared CSS styles for both static and dynamic pages"""
    return """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #2196F3, #21CBF3);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 2em;
            font-weight: 300;
        }
        .content {
            padding: 30px;
        }
        .info-box {
            background: #f8f9fa;
            border-left: 4px solid #2196F3;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 0 8px 8px 0;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        .stat {
            background: #f1f3f4;
            padding: 15px 20px;
            border-radius: 8px;
            flex: 1;
            min-width: 120px;
            text-align: center;
        }
        .stat-number {
            font-size: 1.5em;
            font-weight: bold;
            color: #2196F3;
        }
        .stat-label {
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        th, td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
            color: #333;
        }
        tr:hover {
            background: #f8f9fa;
        }
        a {
            color: #2196F3;
            text-decoration: none;
            font-weight: 500;
        }
        a:hover {
            text-decoration: underline;
        }
        .refresh-btn {
            display: inline-block;
            background: #2196F3;
            color: white;
            padding: 12px 24px;
            border-radius: 6px;
            text-decoration: none;
            margin-top: 20px;
            transition: background 0.3s;
        }
        .refresh-btn:hover {
            background: #1976D2;
            color: white;
            text-decoration: none;
        }
        .footer {
            text-align: center;
            padding: 20px;
            color: #666;
            border-top: 1px solid #eee;
            margin-top: 30px;
        }
    """

def generate_html_page_template(files, title_suffix="", subtitle="Your personal book library in the cloud", 
                              info_text="💡 How to add files:", info_desc="Send EPUB or PDF files to your Telegram bot, or send direct download URLs. Files will appear here automatically.",
                              footer_text="Powered by AWS Lambda • Files are stored securely in S3", use_static_links=False):
    """Generate HTML page using shared template (DRY principle)"""
    file_rows = generate_file_rows(files, use_static_links)
    css = get_html_css()
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>📚 Flibusta File Manager{title_suffix}</title>
        <style>{css}</style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📚 Flibusta File Manager</h1>
                <p>{subtitle}</p>
            </div>
            
            <div class="content">
                <div class="info-box">
                    <strong>{info_text}</strong><br>
                    {info_desc}
                </div>
                
                <div class="stats">
                    <div class="stat">
                        <div class="stat-number">{len(files)}</div>
                        <div class="stat-label">Total Files</div>
                    </div>
                    <div class="stat">
                        <div class="stat-number">{sum(f['size'] for f in files) / (1024*1024):.1f}</div>
                        <div class="stat-label">Total MB</div>
                    </div>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>📖 Filename</th>
                            <th>📊 Size</th>
                            <th>📅 Uploaded</th>
                        </tr>
                    </thead>
                    <tbody>
                        {file_rows}
                    </tbody>
                </table>
                
                <a href="javascript:location.reload()" class="refresh-btn">🔄 Refresh</a>
                
                <div class="footer">
                    <p>{footer_text}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

def generate_static_html_page(files):
    """Generate static HTML page for S3 website hosting with relative file paths"""
    return generate_html_page_template(
        files=files,
        title_suffix=" (Static)",
        subtitle="Static S3 Website - Direct file access",
        info_text="🌐 Static Website:",
        info_desc="This page is hosted directly on S3 with relative file links. Files are accessible without expiring URLs. Add files via the Telegram bot and they'll appear here automatically.",
        footer_text="Static S3 Website • Files accessible via direct links",
        use_static_links=True
    )

def generate_html_page(files):
    """Generate HTML page for file listing (dynamic Lambda version with presigned URLs)"""
    return generate_html_page_template(
        files=files,
        title_suffix="",
        subtitle="Your personal book library in the cloud",
        info_text="💡 How to add files:",
        info_desc="Send EPUB or PDF files to your Telegram bot, or send direct download URLs. Files will appear here automatically.",
        footer_text="Powered by AWS Lambda • Files are stored securely in S3",
        use_static_links=False
    )
