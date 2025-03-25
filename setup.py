from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in site_integration/__init__.py
from site_integration import __version__ as version

setup(
	name="site_integration",
	version=version,
	description="Acepl V13 to Pispl V15 PO-SO Sync",
	author="Chethan",
	author_email="chethan@aerele.in",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
