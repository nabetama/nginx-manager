# ngxmng

## TODO

### Sentinel, Redis.
- Redis Sentinel

### Generate config file.
- Jinja2

#### Sample
```
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('./', encoding='utf8'))
template = env.get_template('./vhost.conf.j2')
nginx_config = template.render(vhost=vhost)
with open("{}.conf".format(fqdn), 'w+') as dest:
  dest.write(nginx_config.encode('utf-8'))
```

### Restart, Reload

#### Candidates.
- Ansible
- subprocess
- python package.
    - Under investigation...
