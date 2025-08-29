from setuptools import find_packages, setup

setup(
    name="online-cli",
    version="0.1",
    py_modules=["client"],
    install_requires=[
        "websockets==12.0",
        "aiohttp==3.9.1",
    ],
    entry_points={
        "console_scripts": [
            "online=client:main",  # online command chaqirilsa -> client.py ichidagi main() ishlaydi
        ],
    },
)
