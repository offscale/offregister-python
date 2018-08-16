from functools import partial

from fabric.api import run
from fabric.context_managers import shell_env, cd
from fabric.contrib.files import exists
from fabric.operations import sudo, _run_command

from offregister_fab_utils.apt import apt_depends


def install_venv0(python3=False, virtual_env=None, *args, **kwargs):
    run_cmd = partial(_run_command, sudo=kwargs.get('use_sudo'))

    ensure_pip_version = lambda: kwargs.get('pip_version') and sudo(
        'pip install pip=={}'.format(kwargs.get('pip_version')))

    home = run('echo $HOME', quiet=True)
    virtual_env = virtual_env or '{home}/venvs/tflow'.format(home=home)

    if python3:
        apt_depends('python3-dev', 'python3-pip', 'python3-wheel', 'python3-venv')
    else:
        apt_depends('python-dev', 'python-pip', 'python-wheel', 'python2.7', 'python2.7-dev', 'python-apt')
        sudo('pip install virtualenv')

    virtual_env_bin = "{virtual_env}/bin".format(virtual_env=virtual_env)
    if not exists(virtual_env_bin):
        run('mkdir -p "{virtual_env_dir}"'.format(virtual_env_dir=virtual_env[:virtual_env.rfind('/')]),
            shell_escape=False)
        if python3:
            run_cmd('python3 -m venv "{virtual_env}"'.format(virtual_env=virtual_env),
                    shell_escape=False)
        else:
            run_cmd('virtualenv "{virtual_env}"'.format(virtual_env=virtual_env), shell_escape=False)

    if not exists(virtual_env_bin):
        raise ReferenceError('Virtualenv does not exist')

    with shell_env(VIRTUAL_ENV=virtual_env, PATH="{}/bin:$PATH".format(virtual_env)):
        ensure_pip_version()
        run_cmd('pip install wheel setuptools')
        return run_cmd('python --version; pip --version')


def install_package1(package_directory, virtual_env, requirements=True, *args, **kwargs):
    run_cmd = partial(_run_command, sudo=kwargs.get('use_sudo'))
    virtual_env = virtual_env or '{home}/venvs/tflow'.format(home=run('echo $HOME', quiet=True))
    with shell_env(VIRTUAL_ENV=virtual_env, PATH="{}/bin:$PATH".format(virtual_env)), cd(package_directory):
        requirements = 'requirements.txt' if requirements is True else requirements
        if requirements:
            if isinstance(requirements, list):
                map(lambda req: run_cmd('pip install -r "{}"'.format(req)),
                    requirements)
            else:
                run_cmd('pip install -r "{}"'.format(requirements))

        return run_cmd('pip uninstall -y "${PWD##*/}"; pip install .;')
