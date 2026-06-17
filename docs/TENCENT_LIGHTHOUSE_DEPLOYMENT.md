# 腾讯云轻量服务器部署记录

本文记录当前试用版在腾讯云轻量应用服务器上的部署方式，便于后续维护、升级和迁移。

## 服务器信息

```text
公网 IP：124.221.239.254
系统：Ubuntu 22.04 LTS
登录用户：ubuntu
访问地址：http://124.221.239.254
```

当前未配置域名和 HTTPS，适合作为小范围公网试用环境。正式长期使用前建议绑定域名并配置 HTTPS。

## 目录结构

```text
/opt/teacher-achievement-system
```

应用代码目录。升级代码时替换此目录下的程序文件。

```text
/var/lib/teacher-achievement-system
```

生产数据目录，包含数据库、上传材料、导出文件和用户导入缓存。升级代码时不要删除该目录。

```text
/var/backups/teacher-achievement
```

自动备份目录。

## 运行服务

系统服务：

```text
teacher-achievement.service
```

常用命令：

```bash
sudo systemctl status teacher-achievement.service
sudo systemctl restart teacher-achievement.service
sudo journalctl -u teacher-achievement.service -f
```

应用实际监听：

```text
127.0.0.1:8001
```

Nginx 对外监听：

```text
80/tcp
```

## 环境变量

生产环境变量文件：

```text
/etc/teacher-achievement-system.env
```

包含：

```text
TEACHER_ACHIEVEMENT_DATA_DIR=/var/lib/teacher-achievement-system
TEACHER_ACHIEVEMENT_SECRET_KEY=随机密钥
PYTHONUNBUFFERED=1
```

该文件权限应保持为：

```bash
sudo chmod 600 /etc/teacher-achievement-system.env
```

## Nginx 配置

站点配置：

```text
/etc/nginx/sites-available/teacher-achievement
/etc/nginx/sites-enabled/teacher-achievement
```

检查和重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

当前上传限制：

```text
client_max_body_size 60m
```

应用本身限制单个材料文件最大 50 MB。

## 防火墙

服务器 UFW 已开放：

```text
22/tcp  SSH
80/tcp  HTTP
443/tcp HTTPS 预留
```

查看状态：

```bash
sudo ufw status
```

腾讯云控制台安全组也需要同步开放 22、80、443。

## 自动备份

备份脚本：

```text
/usr/local/bin/teacher-achievement-backup
```

定时任务：

```text
/etc/cron.d/teacher-achievement-backup
```

当前策略：

```text
每天 02:30 自动备份
保留最近 14 天备份包
```

手动备份：

```bash
sudo /usr/local/bin/teacher-achievement-backup
ls -lh /var/backups/teacher-achievement
```

备份包包含：

- SQLite 数据库快照。
- 上传材料目录。
- 导出文件目录。
- 备份说明文件。

## 试用管理员账号

初始默认密码已在部署时替换为随机临时密码，并设置为首次登录后必须修改。

登录后请立即修改管理员密码，不要继续使用临时密码。

## 升级代码注意事项

升级时只替换：

```text
/opt/teacher-achievement-system
```

不要删除：

```text
/var/lib/teacher-achievement-system
/var/backups/teacher-achievement
/etc/teacher-achievement-system.env
```

升级后执行：

```bash
cd /opt/teacher-achievement-system
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
sudo systemctl restart teacher-achievement.service
```

然后检查：

```bash
curl http://127.0.0.1:8001/health
curl http://124.221.239.254/health
```
