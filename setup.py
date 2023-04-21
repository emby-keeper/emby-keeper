from setuptools import find_packages, setup

with open("README.md") as readme_file:
    readme = readme_file.read()

with open("requirements.txt") as requirements_file:
    requirements = requirements_file.read().splitlines()

setup(
    author="jackzzs",
    author_email="jackzzs@outlook.com",
    python_requires=">=3.7,<3.11",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Natural Language :: Chinese (Simplified)",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    description="Daily checkin automator for emby bots in telegram.",
    install_requires=requirements,
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords=["emby", "telegram", "checkin", "automator"],
    name="embykeeper",
    packages=find_packages(include=["embykeeper", "embykeeper.*"]),
    url="https://github.com/embykeeper/embykeeper",
    version="2.0.9",
    zip_safe=False,
)
