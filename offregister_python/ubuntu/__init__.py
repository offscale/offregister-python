from collections import deque
from functools import partial
from operator import methodcaller
from os import path
from sys import version

from fabric.api import run
from fabric.context_managers import shell_env, cd
from fabric.contrib.files import exists, upload_template
from fabric.operations import sudo, _run_command
from offregister_fab_utils.apt import apt_depends
from offregister_fab_utils.python import pip_depends
from offregister_fab_utils.ubuntu.systemd import restart_systemd
from pkg_resources import resource_filename

from offutils.util import iteritems

offpy_dir = partial(
    path.join,
    path.dirname(resource_filename("offregister_python", "__init__.py")),
    "_config",
)


def install_venv0(python3=False, virtual_env=None, *args, **kwargs):
    run_cmd = partial(_run_command, sudo=kwargs.get("use_sudo", False))

    ensure_pip_version = lambda: kwargs.get("pip_version") and sudo(
        "pip install pip=={}".format(kwargs.get("pip_version"))
    )

    home = kwargs.get("HOMEDIR", run("echo $HOME", quiet=True))
    virtual_env = virtual_env or "{home}/venvs/tflow".format(home=home)

    if python3:
        apt_depends("python3-dev", "python3-pip", "python3-wheel", "python3-venv")
    else:
        apt_depends(
            "python-dev", "python-pip", "python-wheel", "python2.7", "python2.7-dev"
        )  # 'python-apt'
        sudo("pip install virtualenv")

    virtual_env_bin = "{virtual_env}/bin".format(virtual_env=virtual_env)
    if not exists(virtual_env_bin):
        sudo(
            'mkdir -p "{virtual_env_dir}"'.format(
                virtual_env_dir=virtual_env[: virtual_env.rfind("/")]
            ),
            shell_escape=False,
        )
        if python3:
            sudo(
                'python3 -m venv "{virtual_env}"'.format(virtual_env=virtual_env),
                shell_escape=False,
            )
        else:
            sudo(
                'virtualenv "{virtual_env}"'.format(virtual_env=virtual_env),
                shell_escape=False,
            )

    if not exists(virtual_env_bin):
        raise ReferenceError("Virtualenv does not exist")

    if not kwargs.get("use_sudo"):
        user_group = run("echo $(id -un):$(id -gn)", quiet=True)
        sudo(
            "chown -R {user_group} {virtual_env} {home}/.cache".format(
                user_group=user_group, virtual_env=virtual_env, home=home
            )
        )

    with shell_env(VIRTUAL_ENV=virtual_env, PATH="{}/bin:$PATH".format(virtual_env)):
        ensure_pip_version()
        run_cmd("pip install -U wheel setuptools")
        return "Installed: {} {}".format(
            run_cmd("pip --version; python --version"),
            pip_depends(
                "{}/bin/python".format(virtual_env),
                kwargs.get("use_sudo", False),
                kwargs.get("PACKAGES", tuple()),
            ),
        )


def install_package1(
    package_directory, virtual_env=None, requirements=True, *args, **kwargs
):
    run_cmd = partial(_run_command, sudo=kwargs.get("use_sudo"))
    virtual_env = virtual_env or "{home}/venvs/tflow".format(
        home=run("echo $HOME", quiet=True)
    )
    with shell_env(
        VIRTUAL_ENV=virtual_env, PATH="{}/bin:$PATH".format(virtual_env)
    ), cd(package_directory):
        requirements = "requirements.txt" if requirements is True else requirements
        if requirements:
            if isinstance(requirements, list):
                deque(
                    (
                        run_cmd('pip install -r "{}"'.format(req))
                        for req in requirements
                    ),
                    maxlen=0,
                )
            else:
                run_cmd('pip install -r "{}"'.format(requirements))

        return run_cmd('pip uninstall -y "${PWD##*/}"; pip install .;')


def install_circus2(
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
        home=run("echo $HOME", quiet=True)
    )

    conf_dir = "/etc/circus/conf.d"  # '/'.join((taiga_root, 'config'))
    sudo("mkdir -p {conf_dir}".format(conf_dir=conf_dir))
    if not use_sudo:
        user, group = run("echo $(id -un; id -gn)").split(" ")
        sudo(
            "mkdir -p {circus_venv} {virtual_env}".format(
                circus_venv=circus_venv, virtual_env=virtual_env
            )
        )
        sudo(
            "chown -R {user}:{group} {circus_venv} {virtual_env} {conf_dir}".format(
                user=user,
                group=group,
                circus_venv=circus_venv,
                virtual_env=virtual_env,
                conf_dir=conf_dir,
            )
        )
    install_venv0(python3=False, virtual_env=circus_venv, use_sudo=use_sudo)

    run_cmd = partial(_run_command, sudo=use_sudo)
    run_cmd("mkdir -p {circus_home}/logs".format(circus_home=circus_home))
    with shell_env(VIRTUAL_ENV=circus_venv, PATH="{}/bin:$PATH".format(circus_venv)):
        run_cmd("pip install circus")
        py_ver = run("python --version").partition(" ")[2][:3]

    upload_template(
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
            else "\n".join(("{}={}".format(k, v) for k, v in iteritems(circus_env))),
            "PYTHON_VERSION": py_ver,
        },
        use_sudo=use_sudo,
    )
    circusd_context = {"CONF_DIR": conf_dir, "CIRCUS_VENV": circus_venv}
    if exists("/etc/systemd/system"):
        upload_template(
            offpy_dir("circusd.service"),
            "/etc/systemd/system/",
            context=circusd_context,
            use_sudo=True,
            backup=False,
        )
        sudo("systemctl daemon-reload")
    else:
        upload_template(
            offpy_dir("circusd.conf"),
            "/etc/init/",
            context=circusd_context,
            use_sudo=True,
            backup=False,
        )
    return circus_venv


def restart_services3(*args, **kwargs):
    if (
        kwargs.get("circus_args")
        and kwargs.get("circus_name")
        and kwargs.get("circus_home")
    ):
        return restart_systemd("circusd")
