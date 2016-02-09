# coding: utf-8
import daemon.runner
import config
import simplejson as json
import logging
import os
import re
import sys
import subprocess
import time
from redis_db import Redis
from common.logger import Logger
from jinja2 import Environment, FileSystemLoader


def shell_command(command):
    """ コマンド実行する
    @param command shell command.
    @return subprocess.Popen#returncode
    @return res 
    @return err
    """
    p = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    res, err = p.communicate()
    return p.returncode, res, err


class Nx_managerd(object):
    def __init__(self, channels=None):
        if not os.path.isdir(self.directory):
            os.mkdir(self.directory)
        os.chdir(self.directory)
        self.stdin_path = '/dev/null'
        self.stdout_path = os.path.join(self.log_directory, config.STDOUT_LOG)
        self.stderr_path = os.path.join(self.log_directory, config.STDERR_LOG)
        self.pidfile_timeout = 10
        self.pidfile_path = os.path.join(self.directory, config.NX_MANAGERD_PID_FILE)
        self.redis = Redis()
        self.pubsub = self.redis.conn.pubsub()
        self.channels = channels
        if self.channels is None:
            self.channels=['nx']
        self.pubsub.subscribe(self.channels)

    @property
    def is_debug(self):
        return config.IS_DEBUG

    @property
    def log_directory(self):
        if self.is_debug:
            return os.path.expanduser(config.DEBUG_LOG_DIR)
        return os.path.abspath(config.LOG_DIR)

    @property
    def directory(self):
        if self.is_debug:
            return os.path.expanduser(config.DEBUG_DAEMON_DIR)
        return os.path.abspath(config.DAEMON_DIR)

    def run(self):
        while True:
            try:
                for self.item in self.pubsub.listen():
                    if self.parse_json():
                        self.process_do_maintenance()
                        self.process_do_changed_enable()
            except:
                import traceback
                Logger.put(traceback.format_exc())
            finally:
                # コケたら1秒sleep
                Logger.put('Failed SUBSCRIBE')
                # 再度
                self.pubsub.subscribe(self.channels)
                Logger.put('SUBSCRIBE channels {}'.format(self.channels))
                time.sleep(1)

    def process_do_maintenance(self):
        """ メンテナンスの設定を行う
        """
        if self.operation.maintenance_mode:
            self.operation.render_maintenance_config()
            self.operation.cp_maintenance_config()
            self.operation.nginx.restart()
            Logger.put('メンテナンスを{}にしたよ'.format(self.operation.maintenance_mode))

    def process_do_changed_enable(self):
        """ Enableステータスの更新を行う
        """
        self.operation.render_vhost_conf()
        self.operation.cp_vhost_conf()
        self.operation.nginx.reload()

    def parse_json(self):
        init_data = {}
        if not isinstance(self.item['data'], str):
            return False
        try:
            init_data = json.loads(self.item['data'])
        except:
            Logger.put("JSONにできないやつ送られてきた!. {}".format(self.item['data']))
            return False
        self.operation = Operation(init_data)
        return True

class Operation(object):
    def __init__(self, _init_data):
        init_data = _init_data.copy()
        for k, v in init_data.iteritems():
            self.__dict__[k] = v
        os.chdir(self.directory)
        self.nginx = Nginx()
        self.env = Environment(
            loader=FileSystemLoader(
                self.nginx.files_dir, encoding='utf8'
            )
        )

    @property
    def directory(self):
        if config.IS_DEBUG:
            return os.path.expanduser(config.DEBUG_DAEMON_DIR)
        return config.DAEMON_DIR

    def __is_maintenance(self, change):
        """ メンテナンスON/OFFを判断する
        PUB側からのJSONに maintenance ってキーを送ってればメンテにする
        他はメンテにしない。
        @param on_off str
        @return bool
        """
        if hasattr(self, 'maintenance'):
            if self.maintenance == change:
                return True
        return False

    @property
    def maintenance_mode(self):
        if self.__is_maintenance('on') or self.__is_maintenance('off'):
            return self.maintenance
        return False

    def render_maintenance_config(self):
        template = self.env.get_template('nginx.conf.j2')
        nginx_config = template.render(maintenance=self.maintenance_mode)
        with open(self.nginx.maintenance_conf, 'w+') as dest:
            dest.write(nginx_config.encode('utf-8'))
        Logger.put("maintenance.conf作成したよー")

    def cp_maintenance_config(self):
        return self.cp(
            self.nginx.maintenance_conf,
            os.path.join(config.NGINX_CONF_DIR, 'nginx.conf')
        )

    @property
    def __virtual_hosts(self):
        if hasattr(self, 'vhosts'):
            return self.vhosts
        return []

    @property
    def virtual_hosts(self):
        return [VirtualHost(d) for d in self.__virtual_hosts]

    def render_vhost_conf(self):
        template = self.env.get_template('vhost.conf.j2')
        for virtual_host in self.virtual_hosts:
            nginx_config = template.render(virtual_host=virtual_host)
            virtual_host_conf = os.path.join(self.nginx.files_dir, virtual_host.conf)
            with open(virtual_host_conf, 'w+') as dest:
                Logger.put("{}を生成したよー".format(virtual_host_conf))
                dest.write(nginx_config.encode('utf-8'))

    def cp_vhost_conf(self):
        # DEBUG
        return self.cp(
            os.path.join(self.nginx.files_dir, 'vhosts/*'),
            os.path.join(config.NGINX_VHOST_CONF_DIR)
        )

    def cp(self, _from, _to):
        """ cp _from _to
        @param _from str file path
        @param _to str file path
        @return Popen#returncode, res, err
        """
        cp = 'cp -rf {} {}'.format(_from, _to),
        # DEBUG
        Logger.put(cp)
        ret_code, res, err = shell_command(cp)
        return ret_code, res, err


class Nginx(object):
    def reload(self):
        Logger.put("reload nginx...")
        return self.initd('reload')

    def restart(self):
        Logger.put("restart nginx...")
        return self.initd('restart')

    def initd(self, command=None):
        if command is None:
            command = 'reload'
        ret_code, res, err = shell_command('/etc/init.d/nginx {}'.format(command))
        return ret_code, res, err

    @property
    def directory(self):
        if config.IS_DEBUG:
            return os.path.expanduser(config.DEBUG_DAEMON_DIR)
        return config.DAEMON_DIR

    @property
    def files_dir(self):
        return os.path.abspath(
            os.path.join(
            self.directory, 'nx_managerd')
        )

    @property
    def maintenance_conf(self):
        return os.path.abspath(
            os.path.join(self.files_dir, 'maintenance.conf')
        )


class VirtualHost(object):
    pattern = re.compile('mbga-ws(?P<host>\d{3})(?P<port>\d{2})', re.IGNORECASE)

    def __init__(self, init_data):
        self.name = init_data['vhost']
        self.enable = init_data['enable']
        self.__parse()

    def __parse(self):
        matched = self.pattern.match(self.name)
        self.__host_num = matched.groupdict()['host']
        self.port = matched.groupdict()['port']

    @property
    def ap_server(self):
        return 'mbga-es-ap' + str(self.__host_num)

    @property
    def virtual_host(self):
        return self.name

    @property
    def files_dir(self):
        return 'vhosts'

    @property
    def conf(self):
        return os.path.join(self.files_dir, self.virtual_host + '.conf')


def main():
    daemon_runner = daemon.runner.DaemonRunner(Nx_managerd())
    try:
        daemon_runner.do_action()
    except daemon.runner.DaemonRunnerStopFailureError:
        sys.exit(1)


if __name__ == "__main__":
    main()
