from setuptools import setup, find_packages

setup(
    name="ai-api-tester",
    version="0.1.0",
    description="AI-driven API automated testing tool",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    python_requires=">=3.8",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "requests>=2.28.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "ai-tester=lib.cli:main",
        ],
    },
)
