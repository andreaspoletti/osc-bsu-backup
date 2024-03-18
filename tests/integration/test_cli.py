import dataclasses
import logging
import unittest
import warnings
from unittest.mock import patch

import boto3
import botocore

from osc_bsu_backup import cli


class TestIntegrationMethods(unittest.TestCase):
    def setUp(self):
        warnings.filterwarnings(
            "ignore", category=ResourceWarning, message="unclosed.*<ssl.SSLSocket.*>"
        )
        self.region = "eu-west-2"
        endpoint = "https://fcu.eu-west-2.outscale.com"
        config = botocore.config.Config(
            retries={"max_attempts": 10, "mode": "standard"}
        )

        session = boto3.Session()
        self.conn = session.client(
            "ec2", region_name=self.region, endpoint_url=endpoint, config=config
        )

        self.tearDown()

        self.conn.create_key_pair(KeyName="osc_bsu_backup_27aaade4")
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        try:
            self.conn.delete_key_pair(KeyName="osc_bsu_backup_27aaade4")
        except botocore.exceptions.ClientError:
            pass

        vol = self.conn.describe_volumes(
            Filters=[
                {"Name": "tag:Name", "Values": ["osc_bsu_backup_27aaade4"]},
                {"Name": "status", "Values": ["available"]},
            ]
        )
        for i in vol["Volumes"]:
            self.conn.delete_volume(VolumeId=i["VolumeId"])

        snaps = self.conn.describe_snapshots(
            Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
        )
        for i in snaps["Snapshots"]:
            self.conn.delete_snapshot(SnapshotId=i["SnapshotId"])

        vms = self.conn.describe_instances(
            Filters=[
                {"Name": "tag:Name", "Values": ["osc_bsu_backup_27aaade4"]},
                {"Name": "instance-state-name", "Values": ["running"]},
            ]
        )
        for reservation in vms["Reservations"]:
            if reservation.get("Instances"):
                for instance in reservation["Instances"]:
                    self.conn.terminate_instances(InstanceIds=[instance["InstanceId"]])
                    self.conn.stop_instances(
                        InstanceIds=[instance["InstanceId"]], Force=True
                    )

        logging.disable(logging.NOTSET)

    def setup_volumes(self):
        vol1 = self.conn.create_volume(
            AvailabilityZone=self.region + "a", Size=10, VolumeType="standard"
        )
        self.conn.get_waiter("volume_available").wait(VolumeIds=[vol1["VolumeId"]])
        self.conn.create_tags(
            Resources=[vol1["VolumeId"]],
            Tags=[
                {"Key": "Name", "Value": "osc_bsu_backup_27aaade4"},
                {"Key": "test2", "Value": "osc_bsu_backup_27aaade4"},
            ],
        )

        vol2 = self.conn.create_volume(
            AvailabilityZone=self.region + "a", Size=10, VolumeType="standard"
        )
        self.conn.get_waiter("volume_available").wait(VolumeIds=[vol2["VolumeId"]])
        self.conn.create_tags(
            Resources=[vol2["VolumeId"]],
            Tags=[
                {"Key": "Name", "Value": "osc_bsu_backup_27aaade4"},
                {"Key": "test2", "Value": "osc_bsu_backup_27aaade4"},
            ],
        )

        return vol1, vol2

    def setup_instances(self, count=1):
        centos = self.conn.describe_images(
            Filters=[
                {"Name": "owner-alias", "Values": ["Outscale"]},
                {"Name": "name", "Values": ["CentOS-*"]},
            ]
        )

        vm1 = self.conn.run_instances(
            InstanceType="tinav4.c1r1p3",
            ImageId=centos["Images"][0]["ImageId"],
            KeyName="osc_bsu_backup_27aaade4",
            MinCount=1,
            MaxCount=count,
        )

        self.conn.get_waiter("instance_running").wait(
            InstanceIds=[i["InstanceId"] for i in vm1["Instances"]]
        )
        self.conn.create_tags(
            Resources=[i["InstanceId"] for i in vm1["Instances"]],
            Tags=[
                {"Key": "Name", "Value": "osc_bsu_backup_27aaade4"},
                {"Key": "test2", "Value": "osc_bsu_backup_27aaade4"},
            ],
        )

        return vm1

    def test_integration_volume_id(self):
        vol1, _ = self.setup_volumes()

        @dataclasses.dataclass
        class Args:
            volume_id = vol1["VolumeId"]
            instance_id = None
            instances_tags = None
            volumes_tags = None
            profile = None
            region = "eu-west-2"
            endpoint = None
            rotate = 1
            client_cert = None
            rotate_only = False
            rotate_days = None
            copy_tags = False

        with patch("osc_bsu_backup.bsu_backup.DESCRIPTION", "osc_bsu_backup_27aaade4"):
            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 1)

            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 2)

            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 2)

    def test_integration_volume_tags1(self):
        self.setup_volumes()

        @dataclasses.dataclass
        class Args:
            volume_id = None
            instance_id = None
            instances_tags = None
            volumes_tags = [
                "test2:osc_bsu_backup_27aaade4",
                "Name:osc_bsu_backup_27aaade4",
            ]
            profile = None
            region = "eu-west-2"
            endpoint = None
            rotate = 1
            client_cert = None
            rotate_only = False
            rotate_days = None
            copy_tags = False

        with patch("osc_bsu_backup.bsu_backup.DESCRIPTION", "osc_bsu_backup_27aaade4"):
            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 2)

            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 4)

            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 4)

    def test_integration_instance_id(self):
        vm1 = self.setup_instances(count=1)

        @dataclasses.dataclass
        class Args:
            volume_id = None
            instance_id = vm1["Instances"][0]["InstanceId"]
            instances_tags = None
            volumes_tags = None
            profile = None
            region = "eu-west-2"
            endpoint = None
            rotate = 1
            client_cert = None
            rotate_only = False
            rotate_days = None
            copy_tags = False

        with patch("osc_bsu_backup.bsu_backup.DESCRIPTION", "osc_bsu_backup_27aaade4"):
            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 1)

            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 2)

            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 2)

    def test_integration_instance_tags(self):
        self.setup_instances(count=4)

        @dataclasses.dataclass
        class Args:
            volume_id = None
            instance_id = None
            instances_tags = ["test2:osc_bsu_backup_27aaade4"]
            volumes_tags = None
            profile = None
            region = "eu-west-2"
            endpoint = None
            rotate = 1
            client_cert = None
            rotate_only = False
            rotate_days = None
            copy_tags = False

        with patch("osc_bsu_backup.bsu_backup.DESCRIPTION", "osc_bsu_backup_27aaade4"):
            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 4)

            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 8)

            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 8)

    def test_integration_copy_tags(self):
        self.setup_volumes()

        @dataclasses.dataclass
        class Args:
            volume_id = None
            instance_id = None
            instances_tags = None
            volumes_tags = [
                "test2:osc_bsu_backup_27aaade4",
                "Name:osc_bsu_backup_27aaade4",
            ]
            profile = None
            region = "eu-west-2"
            endpoint = None
            rotate = 1
            client_cert = None
            rotate_only = False
            rotate_days = None
            copy_tags = True

        with patch("osc_bsu_backup.bsu_backup.DESCRIPTION", "osc_bsu_backup_27aaade4"):
            self.assertIsNone(cli.backup(Args()))
            snaps = self.conn.describe_snapshots(
                Filters=[{"Name": "description", "Values": ["osc_bsu_backup_27aaade4"]}]
            )
            self.assertEqual(len(snaps["Snapshots"]), 2)
            self.assertEqual(
                snaps["Snapshots"][0]["Tags"],
                [
                    {"Key": "Name", "Value": "osc_bsu_backup_27aaade4"},
                    {"Key": "test2", "Value": "osc_bsu_backup_27aaade4"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
