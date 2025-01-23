from datetime import datetime, timezone
from typing import Optional

import boto3
import botocore
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.type_defs import FilterTypeDef, SnapshotResponseTypeDef

from osc_bsu_backup.error import InputError
from osc_bsu_backup.utils import setup_logging

logger = setup_logging(__name__)

def generate_description() -> str:
    return f"osc-bsu-backup: Automated volume snapshot - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}"

OLD_DESCRIPTION = ["osc-bsu-backup 0.1", "osc-bsu-backup 0.0.2", "osc-bsu-backup 0.0.1"]


def auth(
        profile: Optional[str] = None,
        region: Optional[str] = None,
        client_cert: Optional[str] = None,
        endpoint: Optional[str] = None,
) -> EC2Client:
    default_region = [
        "us-east-2",
        "eu-west-2",
        "ap-northeast-1",
        "us-west-1",
        "cloudgouv-eu-west-1",
    ]

    if not endpoint and region in default_region:
        endpoint = f"https://fcu.{region}.outscale.com"
    elif not endpoint and region not in default_region:
        raise InputError(
            f"You must specify an endpoint when the region is not in: {default_region}"
        )

    logger.info("region: %s", region)
    logger.info("endpoint: %s", endpoint)
    logger.info("profile: %s", profile)

    session = boto3.Session(profile_name=profile)
    conn = session.client(
        "ec2",
        region_name=region,
        endpoint_url=endpoint,
        config=botocore.config.Config(client_cert=client_cert) if client_cert else None,
    )

    logger.info(conn.describe_key_pairs()["KeyPairs"][0])

    return conn


def find_instance_by_id(conn: EC2Client, instance_id: str) -> list[str]:
    logger.info("find the instance by id: %s", instance_id)

    volumes = []
    reservations = conn.describe_instances(InstanceIds=[instance_id])

    for reservation in reservations.get("Reservations", []):
        for instance in reservation["Instances"]:
            logger.info("instance found: %s %s", instance["InstanceId"], instance.get("Tags", []))
            for vol in instance["BlockDeviceMappings"]:
                logger.info("volume found: %s %s", instance["InstanceId"], vol["Ebs"]["VolumeId"])
                volumes.append(vol["Ebs"]["VolumeId"])

    return volumes


def find_volumes_by_tags(conn: EC2Client, tags: list[str]) -> list[str]:
    logger.info("find the volume by tags: %s", tags)

    volumes = []
    filters = [{"Name": f"tag:{tag.split(':')[0]}", "Values": [tag.split(':')[1]]} for tag in tags]

    vol = conn.describe_volumes(Filters=filters)
    for v in vol.get("Volumes", []):
        logger.info("volume found: %s %s", v["VolumeId"], v.get("Tags", []))
        volumes.append(v["VolumeId"])

    return volumes


def create_snapshots(
        conn: EC2Client, volumes: list[str], copy_tags: bool = False
) -> None:
    logger.info("create_snapshot")

    snaps = []

    for vol in volumes:
        description = generate_description()
        snap = conn.create_snapshot(Description=description, VolumeId=vol)

        logger.info("snap create: %s %s", vol, snap["SnapshotId"])
        snaps.append(snap)

        if copy_tags:
            vol_tags = conn.describe_volumes(VolumeIds=[vol])["Volumes"][0].get("Tags", [])
            if vol_tags:
                conn.create_tags(Resources=[snap["SnapshotId"]], Tags=vol_tags)
                logger.info("copy of %s tags to %s", vol, snap["SnapshotId"])

    logger.info("wait for snapshots: %s", [i["SnapshotId"] for i in snaps])
    waiter = conn.get_waiter("snapshot_completed")
    waiter.wait(SnapshotIds=[i["SnapshotId"] for i in snaps])


def rotate_snapshots(
        conn: EC2Client, volumes: list[str], rotate: int = 10, rotate_only: bool = False
) -> None:
    logger.info("rotate_snapshot: %d", rotate)

    for vol in volumes:
        filters = [{"Name": "volume-id", "Values": [vol]}]
        if rotate_only:
            filters.append({"Name": "description", "Values": OLD_DESCRIPTION})

        snaps = conn.describe_snapshots(Filters=filters)

        if len(snaps["Snapshots"]) >= rotate:
            snaps["Snapshots"].sort(key=lambda x: x["StartTime"], reverse=True)

            for i, snap in enumerate(snaps["Snapshots"]):
                if i >= rotate:
                    logger.info("deleting snapshot: %s %s %s", vol, snap["SnapshotId"], snap["StartTime"])

                    try:
                        conn.delete_snapshot(SnapshotId=snap["SnapshotId"])
                    except botocore.exceptions.ClientError as e:
                        if e.response["Error"]["Code"] == "InvalidSnapshot.InUse":
                            logger.error(e)
                        else:
                            raise e


def rotate_days_snapshots(
        conn: EC2Client, volumes: list[str], rotate: int = 10, rotate_only: bool = False
) -> None:
    logger.info("rotate_snapshot: older than %d days", rotate)

    for vol in volumes:
        filters = [{"Name": "volume-id", "Values": [vol]}]
        if rotate_only:
            filters.append({"Name": "description", "Values": OLD_DESCRIPTION})

        snaps = conn.describe_snapshots(Filters=filters)

        for snap in snaps["Snapshots"]:
            if (datetime.now(timezone.utc) - snap["StartTime"]).days >= rotate:
                logger.info("deleting snapshot: %s %s %s", vol, snap["SnapshotId"], snap["StartTime"])

                try:
                    conn.delete_snapshot(SnapshotId=snap["SnapshotId"])
                except botocore.exceptions.ClientError as e:
                    if e.response["Error"]["Code"] == "InvalidSnapshot.InUse":
                        logger.error(e)
                    else:
                        raise e


def find_instances_by_tags(conn: EC2Client, tags: list[str]) -> list[str]:
    logger.info("find the instance by tags: %s", tags)

    volumes = []
    filters = [{"Name": "instance-state-name", "Values": ["running", "stopped"]}]
    filters.extend([{"Name": f"tag:{tag.split(':')[0]}", "Values": [tag.split(':')[1]]} for tag in tags])

    reservations = conn.describe_instances(Filters=filters)
    for reservation in reservations.get("Reservations", []):
        for instance in reservation["Instances"]:
            logger.info("instance found: %s %s", instance["InstanceId"], instance.get("Tags", []))
            for vol in instance["BlockDeviceMappings"]:
                logger.info("volume found: %s %s", instance["InstanceId"], vol["Ebs"]["VolumeId"])
                volumes.append(vol["Ebs"]["VolumeId"])

    return volumes