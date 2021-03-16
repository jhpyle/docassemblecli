from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="docassemblecli",
    version="0.0.5",
    author="Jonathan Pyle",
    author_email="jhpyle@gmail.com",
    description="CLI utilities for using docassemble",
    install_requires=['pyyaml', 'requests'],
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jhpyle/docassemblecli",
    project_urls={
        "Bug Tracker": "https://github.com/jhpyle/docassemblecli/issues",
    },
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(),
    python_requires=">=2.7",
    scripts=['bin/dainstall']
)
