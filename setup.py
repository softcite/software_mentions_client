#!/usr/bin/env python

from setuptools import setup, find_packages

with open('requirements.txt', 'r') as f:
    reqs = f.readlines()

setup(
    name="software_mentions_client",
    version="0.1.9",
    author="Patrice Lopez",
    author_email="patrice.lopez@science-miner.com",
    description="A client for extracting software mentions in scholar publications",
    long_description=open("Readme.md", encoding='utf-8').read(),
    long_description_content_type="text/markdown",
    url='https://github.com/kermitt2/software_mentions_client',
    packages=find_packages(exclude=["*.tests", "*.tests.*", "tests.*", "tests", "my_config*", "*.log"]),
    python_requires='>=3.5',
    install_requires=reqs,
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3.5",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)
