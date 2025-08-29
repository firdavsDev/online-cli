from setuptools import setup

setup(
    name="online-cli",
    version="0.2",
    py_modules=["client"],
    install_requires=["aiohttp==3.9.1"],
    entry_points={
        "console_scripts": [
            "online=client:main",
        ],
    },
)
