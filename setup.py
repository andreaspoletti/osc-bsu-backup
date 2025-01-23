# -*- coding:utf-8 -*-
from setuptools import find_packages, setup
from osc_bsu_backup import __version__

setup(
    name="osc-bsu-backup",
    version=__version__,
    packages=find_packages(),
    author="Outscale SAS",
    author_email="remi.jouannet@outscale.com",
    description="Outscale BSU Backup tool",
    url="http://www.outscale.com/",
    python_requires=">=3.7",
    entry_points={
        "console_scripts": ["osc-bsu-backup = osc_bsu_backup.cli:main"]
    },
    install_requires=[
        "boto3~=1.36.4",
        "botocore~=1.36.4",
        "mypy~=1.14.1",
        "mypy_boto3_ec2",
        "typing_extensions>=4.6.0",
        "mypy_extensions>=1.0.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
)