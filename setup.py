import pathlib
from setuptools import setup

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

# This call to setup() does all the work
setup(
    name="liteserver",
    version="2.0.0",# 2023-03-20
    description="Lightweight control system for scientific instruments. Like EPICS but much simpler",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/ASukhanov/liteServer",
    author="Andrei Sukhanov",
    author_email="sukhanov@bnl.gov",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
    ],
    packages=["liteserver","liteserver.device"],
    include_package_data=True,
    install_requires=["msgpack"],
    #entry_points={
    #    "console_scripts": [
    #        "liteServer=liteServer.__main__:main",
    #    ]
    #},
)
