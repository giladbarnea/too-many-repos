# -*- coding: utf-8 -*-
from setuptools import setup

packages = ["too_many_repos"]

package_data = {"": ["*"]}

install_requires = ["click>=7.1,<8.0", "rich>=9.0"]

setup_kwargs = {
    "name": "too-many-repos",
    "version": "0.0.2",
    "description": "A command-line tool for lazy people with too many projects",
    "long_description": None,
    "author": "Gilad Barnea",
    "author_email": "giladbrn@gmail.com",
    "maintainer": None,
    "maintainer_email": None,
    "url": None,
    "packages": packages,
    "package_data": package_data,
    "install_requires": install_requires,
    "python_requires": ">=3.8,<4.0",
    "entry_points": {
        "console_scripts": [
            "tmr = too_many_repos.too_many_repos:main",
        ]
    },
}

setup(**setup_kwargs)
