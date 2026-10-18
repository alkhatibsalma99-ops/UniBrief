
import os

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()


def get_r2_client():
    required_variables = [
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT_URL",
        "R2_BUCKET_NAME",
    ]

    missing = [
        name
        for name in required_variables
        if not os.getenv(name)
    ]

    if missing:
        raise RuntimeError(
            "Missing R2 configuration: "
            + ", ".join(missing)
        )

    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={
                "max_attempts": 3,
                "mode": "standard",
            },
        ),
    )


def upload_file_to_r2(
    file_bytes: bytes,
    object_key: str,
):
    client = get_r2_client()

    client.put_object(
        Bucket=os.environ["R2_BUCKET_NAME"],
        Key=object_key,
        Body=file_bytes,
        ContentType="application/pdf",
    )

    return object_key


def download_file_from_r2(
    object_key: str,
) -> bytes:
    client = get_r2_client()

    response = client.get_object(
        Bucket=os.environ["R2_BUCKET_NAME"],
        Key=object_key,
    )

    try:
        return response["Body"].read()
    finally:
        response["Body"].close()


def delete_file_from_r2(
    object_key: str,
):
    client = get_r2_client()

    client.delete_object(
        Bucket=os.environ["R2_BUCKET_NAME"],
        Key=object_key,
    )
