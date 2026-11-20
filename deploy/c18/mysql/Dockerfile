FROM mysql@sha256:a81d043930e51745522bd5c430961cf8286f0a23f0a9a2a6e0108f7ea71b0902 AS official

FROM oraclelinux@sha256:59431c7e33419d7f28a2c8bb94c77fffea3f4ee3d07583940d7172736932a93b

ARG MYSQL_VERSION=8.4.13-1.el9
ARG MYSQL_GPG_SHA256=a4bcd9f16a53cc763f87b9955dbcdced33c7aa90296b157eb6ceef0f156f4327

RUN microdnf upgrade -y \
    && microdnf install -y ca-certificates \
    && curl -fsSLo /tmp/RPM-GPG-KEY-mysql https://repo.mysql.com/RPM-GPG-KEY-mysql-2025 \
    && echo "${MYSQL_GPG_SHA256}  /tmp/RPM-GPG-KEY-mysql" | sha256sum -c - \
    && rpm --import /tmp/RPM-GPG-KEY-mysql \
    && printf '%s\n' \
      '[mysql-8.4-minimal]' \
      'name=MySQL 8.4 minimal' \
      'baseurl=https://repo.mysql.com/yum/mysql-8.4-community/docker/el/9/$basearch/' \
      'enabled=1' \
      'gpgcheck=1' \
      'gpgkey=file:///tmp/RPM-GPG-KEY-mysql' \
      > /etc/yum.repos.d/mysql-community-minimal.repo \
    && microdnf install -y "mysql-community-server-minimal-${MYSQL_VERSION}" \
    && rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE} %{SIGPGP:pgpsig}\n' mysql-community-server-minimal \
    && test "$(rpm -q --qf '%{VERSION}-%{RELEASE}' mysql-community-server-minimal)" = "${MYSQL_VERSION}" \
    && rpm -V mysql-community-server-minimal \
    && microdnf clean all \
    && rm -rf /tmp/* /var/cache/dnf \
    && install -d -o mysql -g mysql -m 0700 /var/lib/mysql \
    && install -d -o mysql -g mysql -m 0750 /var/run/mysqld /var/lib/mysql-files /docker-entrypoint-initdb.d

COPY --from=official /usr/local/bin/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY --chmod=0444 init-kfp-databases.sql /docker-entrypoint-initdb.d/01-kfp-databases.sql
COPY --chmod=0444 grant-kfp-databases.sh /docker-entrypoint-initdb.d/02-grant-kfp-databases.sh

USER mysql:mysql
VOLUME /var/lib/mysql
EXPOSE 3306 33060
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["mysqld"]
