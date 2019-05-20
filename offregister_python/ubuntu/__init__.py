from functools import partial
from os import path

from fabric.api import run
from fabric.context_managers import shell_env, cd
from fabric.contrib.files import exists, upload_template
from fabric.operations import sudo, _run_command, put

from offregister_fab_utils.apt import apt_depends
from offregister_fab_utils.ubuntu.systemd import restart_systemd, install_upgrade_service
from pkg_resources import resource_filename

offpy_dir = partial(path.join, path.dirname(resource_filename('offregister_python', '__init__.py')), '_config')


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


def install_uwsgi2(package_directory, virtual_env,
                   python3=False, entrypoint=None, *args, **kwargs):
    if entrypoint is None:
        return 'skipping install_uwsgi2, no endpoint specified'


def install_circus3(circus_args=None, circus_name=None, circus_home=None,
                    circus_venv='/opt/venvs/circus', remote_user='ubuntu', use_sudo=False, *args, **kwargs):
    if circus_args is None or circus_name is None or circus_home is None:
        return 'insufficient args, skipping circus'

    if not use_sudo:
        sudo('mkdir -p {circus_venv}'.format(circus_venv=circus_venv))
        sudo('chown -R $USER:$GROUP {circus_venv}'.format(circus_venv=circus_venv))
    install_venv0(python3=False, virtual_env=circus_venv, use_sudo=use_sudo)

    run_cmd = partial(_run_command, sudo=use_sudo)
    with shell_env(VIRTUAL_ENV=circus_venv, PATH="{}/bin:$PATH".format(circus_venv)):
        run_cmd('pip install circus')
        py_ver = run('ython --version').partition(' ')[2][:3]

    conf_dir = '/etc/circus/conf.d'  # '/'.join((taiga_root, 'config'))
    sudo('mkdir -p {conf_dir}'.format(conf_dir=conf_dir))

    upload_template(offpy_dir('circus.ini'), '{conf_dir}/'.format(conf_dir=conf_dir),
                    context={'ENDPOINT_PORT': 5555,
                             'WORKING_DIR': kwargs.get('circus_working_dir', circus_home),
                             'ARGS': circus_args,
                             'NAME': circus_name,
                             'USER': remote_user,
                             'HOME': circus_home,
                             'VENV': circus_venv,
                             'PYTHON_VERSION': py_ver},
                    use_sudo=True)
    circusd_context = {'CONF_DIR': conf_dir, 'CIRCUS_VENV': circus_venv}
    if exists('/etc/systemd/system'):
        upload_template(offpy_dir('circusd.service'), '/etc/systemd/system/', context=circusd_context, use_sudo=True)
    else:
        upload_template(offpy_dir('circusd.conf'), '/etc/init/', context=circusd_context, use_sudo=True)
    return circus_venv


def uwsgi(package_directory, virtual_env, python3=False, entrypoint=None, *args, **kwargs):
    with shell_env(VIRTUAL_ENV=virtual_env, PATH="{}/bin:$PATH".format(virtual_env)), cd(package_directory):
        _run_command('pip install uwsgi', sudo=kwargs.get('use_sudo') or False)
    name = kwargs.get('name', path.basename(package_directory))
    sudo('mkdir -p /etc/uwsgi/{apps-enabled,apps-available} /var/log/uwsgi/app/')

    apps_enabled_ini = '/etc/uwsgi/apps-enabled/{name}.ini'.format(name=name)
    apps_available_ini = '/etc/uwsgi/apps-available/{name}.ini'.format(name=name)
    sudo('rm -f {apps_enabled_ini} {apps_available_ini}'.format(apps_enabled_ini=apps_enabled_ini,
                                                                apps_available_ini=apps_available_ini))
    upload_template(offpy_dir('bottle.ini'), apps_available_ini,
                    context={'GID': 'ubuntu',
                             'UID': 'ubuntu',
                             'VIRTUALENV': virtual_env,
                             'PYTHONHOME': virtual_env,
                             'PYTHONPATH': '{virtual_env}/bin'.format(virtual_env=virtual_env),
                             'ENTRYPOINT': entrypoint,
                             'MODULE_NAME': name.replace('-', '_'),
                             'WORKING_DIRECTORY': package_directory,
                             'NAME': name},
                    use_sudo=True, backup=False)
    sudo('ln -s {apps_available_ini} {apps_enabled_ini}'.format(apps_available_ini=apps_available_ini,
                                                                apps_enabled_ini=apps_enabled_ini))
    # uwsgi service
    emperor_ini = '/etc/uwsgi-emperor/emperor.ini'

    python_version = 3 if python3 else 2
    service_name = 'venv-py{python_version}-uwsgi'.format(python_version=python_version)
    conf_remote_filename = '/lib/systemd/system/{service_name}.service'.format(service_name=service_name)
    upload_template(offpy_dir('uwsgi.service'), conf_remote_filename,
                    context={
                        'PYTHON_VERSION': python_version,
                        'UWSGI_BINARY': '{virtual_env}/bin/uwsgi'.format(virtual_env=virtual_env),
                        'UWSGI_EMPEROR_INI': emperor_ini
                    },
                    use_sudo=True, backup=False)

    # uwsgi emperor
    sudo('mkdir -p /etc/uwsgi-emperor/vassals')
    with open(offpy_dir('uwsgi-emperor.ini')) as f:
        put(f, emperor_ini, use_sudo=True)


def restart_services4(*args, **kwargs):
    restart_systemd('nginx')

    if 'entrypoint' not in kwargs:
        return

    python_version = 3 if kwargs.get('python3') else 2
    service_name = 'venv-py{python_version}-uwsgi'.format(python_version=python_version)

    restart_systemd(service_name)
