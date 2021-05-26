asnakedeck
_________________

[![PyPI version](https://badge.fury.io/py/asnakedeck.svg)](http://badge.fury.io/py/asnakedeck)
[![Test Status](https://github.com/ashb/asnakedeck/workflows/Test/badge.svg?branch=develop)](https://github.com/ashb/asnakedeck/actions?query=workflow%3ATest)
[![Lint Status](https://github.com/ashb/asnakedeck/workflows/Lint/badge.svg?branch=develop)](https://github.com/ashb/asnakedeck/actions?query=workflow%3ALint)
[![codecov](https://codecov.io/gh/ashb/asnakedeck/branch/main/graph/badge.svg)](https://codecov.io/gh/ashb/asnakedeck)
[![License](https://img.shields.io/github/license/mashape/apistatus.svg)](https://pypi.python.org/pypi/asnakedeck/)
[![Downloads](https://pepy.tech/badge/asnakedeck)](https://pepy.tech/project/asnakedeck)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://timothycrosley.github.io/isort/)
_________________

[Read Latest Documentation](https://ashb.github.io/asnakedeck/) - [Browse GitHub Code Repository](https://github.com/ashb/asnakedeck/)
_________________

**asnakedeck** AsnycIO StreamDeck controller for Linux

This started out as a clone/hack on [jpetazzo/snakedeck](https://github.com/jpetazzo/snakedeck) but has evolved.

This project

- Uses AsyncIO wherever possible (sadly the reading/polling of the USB device is still threaded)

- Is implemented as packages, not just a flat script


License
-------

This project itself is license under the MIT license.
