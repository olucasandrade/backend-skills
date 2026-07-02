import boto3

# Vulnerable: real-shaped AWS credentials committed directly in source
# instead of pulled from environment/secret manager. The scan.py secrets
# pass should catch this one deterministically (high confidence).
AWS_ACCESS_KEY_ID = "AKIAABCDEFGHIJKLMNOP"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)
