#!/usr/bin/env python

from distutils.core import setup
from build_ext_packages import __version__

setup(
    name='extjs-python-builder',
    version=__version__,
    description='Build ExtJS codebase and create a packaged build (concatenated, compressed, etc).',
    author='Bas van Oostveen',
    author_email='v.oostveen@gmail.com',
    py_modules=['build_ext_packages'],
)

