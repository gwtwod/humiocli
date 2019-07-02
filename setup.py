# -*- coding: utf-8 -*-

# DO NOT EDIT THIS FILE!
# This file has been autogenerated by dephell <3
# https://github.com/dephell/dephell

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import os.path

readme = ''
here = os.path.abspath(os.path.dirname(__file__))
readme_path = os.path.join(here, 'README.rst')
if os.path.exists(readme_path):
    with open(readme_path, 'rb') as stream:
        readme = stream.read().decode('utf8')

setup(
    long_description=readme,
    name='humiocli',
    version='0.2.4',
    description='Command line interface for interacting with Humio API using the humiocore library',
    python_requires='==3.*,>=3.6.0',
    project_urls={'repository': 'https://github.com/gwtwod/py3humiocli'},
    author='Jostein Haukeli',
    entry_points={'console_scripts': ['hc = humiocli.cli:cli']},
    packages=['humiocli'],
    package_data={},
    install_requires=[
        'chardet==3.*,>=3.0.0', 'click==7.*,>=7.0.0', 'humiocore',
        'pandas==0.*,>=0.24.1', 'pendulum==2.*,>=2.0.0',
        'pygments==2.*,>=2.3.0', 'pytz==2018.*,>=2018.9.0',
        'snaptime==0.*,>=0.2.4', 'structlog==19.*,>=19.1.0',
        'tabulate==0.*,>=0.8.3', 'tzlocal==1.*,>=1.5.0'
    ],
    dependency_links=[
        'git+https://github.com/gwtwod/py3humiocore.git@a1f614c02b2b9494754e59e3bf89e60de74c2fe2#egg=humiocore'
    ],
    extras_require={'dev': ['black', 'pylint==2.*,>=2.3.0']},
)
