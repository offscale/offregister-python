# -*- coding: utf-8 -*-
from collections import deque, namedtuple
from functools import partial
from os import path
from sys import version

if version[0] == "2":
    try:
        from cStringIO import StringIO
    except ImportError:
        from StringIO import StringIO
else:
    from io import StringIO

from offregister_fab_utils.apt import apt_depends
from offregister_fab_utils.misc import upload_template_fmt
from offregister_fab_utils.python import pip_depends
from offregister_fab_utils.ubuntu.systemd import restart_systemd
from offutils import pp
from offutils.util import iteritems
from patchwork.files import exists
from pkg_resources import resource_filename

offpy_dir = partial(
    path.join,
    path.dirname(resource_filename("offregister_python", "__init__.py")),
    "_config",
)


def install_venv0(
    c, python3=False, virtual_env=None, system_site_packages=False, *args, **kwargs
):
    """
    :param c: Connection
    :type c: ```fabric.connection.Connection```

    :param python3: Whether to use Python 3 (`False` for Python 2)
    :type python3: ```bool```

    :param virtual_env: Virtualenv path, defaults to "{home}/venvs/tflow"
    :type virtual_env: ```Optional[str]```

    :param system_site_packages: Whether to create virtualenv with `--system-site-packages`
    :type system_site_packages: ```bool```

    :return: Install string showing what was installed
    :rtype: ```str```
    """
    run_cmd = c.sudo if kwargs.get("use_sudo", False) else c.run

    home = kwargs.get("HOMEDIR", c.run("echo $HOME", hide=True).stdout.rstrip())
    virtual_env = virtual_env or "{home}/venvs/tflow".format(home=home)

    if python3:
        apt_depends(
            c,
            "python3-dev",
            "python3-pip",
            "python3-wheel",
            "python3-venv",
            "libssl-dev",
            "libffi-dev",
        )
        python_bin = "python3"
    else:
        apt_depends(
            c,
            "python-dev",
            "python-pip",
            "python-wheel",
            "python2.7",
            "python2.7-dev",
            "libssl-dev",
            "libffi-dev",
        )
        # 'python-apt'
        c.sudo("python -m pip install virtualenv")
        python_bin = "python"

    ensure_pip_version = lambda _run_cmd: kwargs.get("pip_version") and _run_cmd(
        "{python_bin} -m pip install {pip_args}".format(
            python_bin=python_bin,
            pip_args=kwargs["pip_version"]
            if kwargs["pip_version"].startswith("-")
            else "=={pip_version}".format(pip_version=kwargs["pip_version"]),
        )
    )

    virtual_env_bin = "{virtual_env}/bin".format(virtual_env=virtual_env)
    if not exists(c, runner=c.run, path=virtual_env_bin):
        c.sudo(
            'mkdir -p "{virtual_env_dir}"'.format(
                virtual_env_dir=virtual_env[: virtual_env.rfind("/")]
            )
        )
        if python3:
            c.sudo(
                '{python_bin} -m venv "{virtual_env}"{extra_args}'.format(
                    python_bin=python_bin,
                    virtual_env=virtual_env,
                    extra_args=" --system-site-packages"
                    if system_site_packages
                    else "",
                )
            )
        else:
            c.sudo(
                'virtualenv "{virtual_env}"{extra_args}'.format(
                    virtual_env=virtual_env,
                    extra_args=" --system-site-packages"
                    if system_site_packages
                    else "",
                )
            )

    if not exists(c, runner=c.run, path=virtual_env_bin):
        raise ReferenceError("Virtualenv does not exist")

    if not kwargs.get("use_sudo"):
        user_group = c.run("echo $(id -un):$(id -gn)", hide=True).stdout.rstrip()
        c.sudo(
            "chown -R {user_group} {virtual_env}"
            " && ( test -d {home}/.cache && chown -R {user_group} {home}/.cache"
            "      || true )".format(
                user_group=user_group, virtual_env=virtual_env, home=home
            )
        )

    env = {"VIRTUAL_ENV": virtual_env, "PATH": "{}/bin:$PATH".format(virtual_env)}
    env["PYTHONPATH"] = env["PATH"]
    ensure_pip_version(c.run)
    pp({"offregister-python/offregister_python/deb_shared.py": env})
    run_cmd(
        "{python_bin} -m pip --version "
        "{python_bin} --version ; "
        "which {python_bin} ; ".format(python_bin=python_bin),
        env=env,
        replace_env=True,
    )
    run_cmd(
        "{python_bin} -m pip install -U wheel setuptools".format(python_bin=python_bin),
        env=env,
    )
    return "Installed: {} {}".format(
        run_cmd(
            "{python_bin} -m pip --version; {python_bin} --version".format(
                python_bin=python_bin
            )
        ),
        pip_depends(
            c,
            "{}/bin/{}".format(virtual_env, python_bin),
            kwargs.get("use_sudo", False),
            kwargs.get("packages", tuple()),
        ),
    )


def install_package1(
    c,
    package_directory,
    virtual_env=None,
    requirements=True,
    dependencies=None,
    *args,
    **kwargs
):
    """
    :param c: Connection
    :type c: ```fabric.connection.Connection```

    :param package_directory: Directory with the first set of Python files (e.g.: setup.py, requirements.txt)
    :type package_directory: ```str```

    :param virtual_env: Virtualenv path, defaults to "{home}/venvs/tflow"
    :type virtual_env: ```Optional[str]```

    :param requirements: Whether to `pip install -r requirements.txt`
    :type requirements: ```bool```

    :param dependencies: If non-empty will `pip install ${dependencies}`
    :type dependencies: ```Optional[str]```

    :return: (stdout, stderr, exited)
    :rtype: ```Tuple[IO, IO, int]```
    """
    run_cmd = c.sudo if kwargs.get("use_sudo", False) else c.run
    virtual_env = virtual_env or "{home}/venvs/tflow".format(
        home=c.run("echo $HOME", hide=True).stdout.rstrip()
    )
    env = dict(VIRTUAL_ENV=virtual_env, PATH="{}/bin:$PATH".format(virtual_env))
    with c.cd(package_directory):
        requirements = "requirements.txt" if requirements is True else requirements
        if requirements:
            if isinstance(requirements, list):
                deque(
                    (
                        run_cmd('python -m pip install -r "{}"'.format(req), env=env)
                        for req in requirements
                    ),
                    maxlen=0,
                )
            elif exists(c, runner=run_cmd, path="requirements.txt"):
                run_cmd('python -m pip install -r "{}"'.format(requirements), env=env)

        if dependencies:
            if isinstance(dependencies, (str, bytes)):
                run_cmd("python -m pip install {}".format(dependencies), env=env)
            else:
                deque(
                    map(
                        partial(run_cmd, env=env),
                        map("python -m pip install {}".format, dependencies),
                    ),
                    maxlen=0,
                )

        if exists(c, runner=run_cmd, path="setup.py"):
            return run_cmd(
                'python -m pip uninstall -y "${PWD##*/}"; python -m pip install .;',
                env=env,
            )
        io = StringIO()
        return namedtuple("_", ("stdout", "stderr", "exited"))(io, io, 0)


def install_circus2(
    c,
    circus_env=None,
    circus_cmd=None,
    circus_args=None,
    circus_name=None,
    circus_home=None,
    circus_venv="/opt/venvs/circus",
    remote_user="ubuntu",
    virtual_env=None,
    use_sudo=False,
    *args,
    **kwargs
):
    if (
        circus_cmd is None
        or circus_args is None
        or circus_name is None
        or circus_home is None
    ):
        return "insufficient args, skipping circus"

    virtual_env = virtual_env or "{home}/venvs/tflow".format(
        home=c.run("echo $HOME", hide=True).stdout.rstrip()
    )

    conf_dir = "/etc/circus/conf.d"  # '/'.join((taiga_root, 'config'))
    c.sudo("mkdir -p {conf_dir}".format(conf_dir=conf_dir))
    if not use_sudo:
        user, group = c.run("echo $(id -un; id -gn)").stdout.rstrip().split(" ")
        c.sudo(
            "mkdir -p {circus_venv} {virtual_env}".format(
                circus_venv=circus_venv, virtual_env=virtual_env
            )
        )
        c.sudo(
            "chown -R {user}:{group} {circus_venv} {virtual_env} {conf_dir}".format(
                user=user,
                group=group,
                circus_venv=circus_venv,
                virtual_env=virtual_env,
                conf_dir=conf_dir,
            )
        )
    install_venv0(c, python3=False, virtual_env=circus_venv, use_sudo=use_sudo)

    run_cmd = c.sudo if kwargs.get("use_sudo", False) else c.run
    run_cmd("mkdir -p {circus_home}/logs".format(circus_home=circus_home))
    env = dict(VIRTUAL_ENV=circus_venv, PATH="{}/bin:$PATH".format(circus_venv))
    run_cmd("python -m pip install circus", env=env)
    py_ver = c.run("python --version", env=env).stdout.partition(" ")[2][:3]

    upload_template_fmt(
        c,
        offpy_dir("circus.ini"),
        "{conf_dir}/".format(conf_dir=conf_dir),
        context={
            "ENDPOINT_PORT": 5555,
            "WORKING_DIR": kwargs.get("circus_working_dir", circus_home),
            "CMD": circus_cmd,
            "ARGS": circus_args,
            "NAME": circus_name,
            "USER": remote_user,
            "HOME": circus_home,
            "VENV": virtual_env,
            "CIRCUS_ENV": ""
            if circus_env is None
            else "\n".join("{}={}".format(k, v) for k, v in iteritems(circus_env)),
            "PYTHON_VERSION": py_ver,
        },
        # use_sudo=use_sudo,
    )
    circusd_context = {"CONF_DIR": conf_dir, "CIRCUS_VENV": circus_venv}
    if exists(c, runner=c.run, path="/etc/systemd/system"):
        upload_template_fmt(
            c,
            offpy_dir("circusd.service"),
            "/etc/systemd/system/",
            context=circusd_context,
            use_sudo=True,
            backup=False,
        )
        c.sudo("systemctl daemon-reload")
    else:
        upload_template_fmt(
            c,
            offpy_dir("circusd.conf"),
            "/etc/init/",
            context=circusd_context,
            use_sudo=True,
            backup=False,
        )
    return circus_venv


def restart_services3(c, *args, **kwargs):
    """
    :param c: Connection
    :type c: ```fabric.connection.Connection```

    :return: res.stdout if res.exited == 0 else res.stderr
    :rtype: ```str```
    """
    if (
        kwargs.get("circus_args")
        and kwargs.get("circus_name")
        and kwargs.get("circus_home")
    ):
        return restart_systemd(c, "circusd")


__all__ = ["install_venv0", "install_package1", "install_circus2", "restart_services3"]
