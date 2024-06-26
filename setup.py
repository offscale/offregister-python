# -*- coding: utf-8 -*-

"""
setup.py implementation, interesting because it parsed the first __init__.py and
    extracts the `__author__` and `__version__`
"""

import sys
from ast import Assign, Name, parse
from functools import partial
from itertools import chain
from operator import attrgetter
from os import listdir, path
from os.path import extsep

from setuptools import find_packages, setup

if sys.version_info[:2] >= (3, 12):
    from ast import Del as Str
else:
    from ast import Str

    if sys.version_info[0] == 2:
        from itertools import ifilter as filter
        from itertools import imap as map

if sys.version_info[:2] > (3, 7):
    from ast import Constant
else:
    from ast import expr

    # Constant. Will never be used in Python =< 3.8
    Constant = type("Constant", (expr,), {})


package_name_verbatim = "offregister-python"
package_name = package_name_verbatim.replace("-", "_")

with open(
    path.join(path.dirname(__file__), "README{extsep}md".format(extsep=extsep)), "rt"
) as fh:
    long_description = fh.read()


def gen_join_on_pkg_name(*paths):
    """
    Create a function that joins on `os.path.join` from the package name onward

    :param paths: one or more str, referring to relative folder names
    :type paths: ```*paths```

    :return: function that joins on `os.path.join` from the package name onward
    :rtype: ```Callable[tuple[str, ...], str]```
    """
    return partial(path.join, path.dirname(__file__), package_name, *paths)


def main():
    """Main function for setup.py; this actually does the installation"""
    with open(
        path.join(
            path.abspath(path.dirname(__file__)),
            package_name,
            "__init__{extsep}py".format(extsep=extsep),
        )
    ) as f:
        parsed_init = parse(f.read())

    __author__, __version__, __description__ = map(
        lambda node: node.value if isinstance(node, Constant) else node.s,
        filter(
            lambda node: isinstance(node, (Constant, Str)),
            map(
                attrgetter("value"),
                filter(
                    lambda node: isinstance(node, Assign)
                    and any(
                        filter(
                            lambda name: isinstance(name, Name)
                            and name.id
                            in frozenset(
                                ("__author__", "__version__", "__description__")
                            ),
                            node.targets,
                        )
                    ),
                    parsed_init.body,
                ),
            ),
        ),
    )
    _data_join = gen_join_on_pkg_name("_data")
    _config_join = gen_join_on_pkg_name("_config")

    setup(
        name=package_name_verbatim,
        author=__author__,
        author_email="807580+SamuelMarks@users.noreply.github.com",
        version=__version__,
        url="https://github.com/offscale/{}".format(package_name_verbatim),
        description=__description__,
        long_description=long_description,
        long_description_content_type="text/markdown",
        classifiers=[
            "Development Status :: 7 - Inactive",
            "Intended Audience :: Developers",
            "Topic :: Software Development",
            "Topic :: Software Development :: Libraries :: Python Modules",
            "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication",
            "License :: OSI Approved :: Apache Software License",
            "License :: OSI Approved :: MIT License",
            "Programming Language :: Python",
            "Programming Language :: Python :: 2",
            "Programming Language :: Python :: 2.7",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.5",
            "Programming Language :: Python :: 3.6",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "Programming Language :: Python :: 3.13",
        ],
        license="(Apache-2.0 OR MIT OR CC0-1.0)",
        license_files=["LICENSE-APACHE", "LICENSE-MIT", "LICENSE-CC0"],
        install_requires=[
            "pyyaml",
            "invoke >= 2.0 ; python_version>='3.5'",
            "fabric >= 2.7.1 ; python_version>='3.5'",
            "fabric == 2.7.1 ; python_version<'3.5'",
        ],
        test_suite="{}{}tests".format(package_name, path.extsep),
        packages=find_packages(),
        package_data={
            package_name: list(
                chain.from_iterable(
                    map(
                        lambda folder_join: map(
                            folder_join,
                            listdir(folder_join()),
                        ),
                        (_data_join, _config_join),
                    )
                )
            )
        },
        include_package_data=True,
    )


def setup_py_main():
    """Calls main if `__name__ == '__main__'`"""
    if __name__ == "__main__":
        main()


setup_py_main()
