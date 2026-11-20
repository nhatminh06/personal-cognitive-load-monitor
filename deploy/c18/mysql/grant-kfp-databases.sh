if ! declare -F docker_process_sql >/dev/null; then
    . /usr/local/bin/docker-entrypoint.sh
    SOCKET=/var/lib/mysql/mysql.sock
    ready=false
    for _ in {1..120}; do
        if docker_process_sql --database=mysql <<<'SELECT 1;' >/dev/null 2>&1; then
            ready=true
            break
        fi
        sleep 1
    done
    [ "$ready" = true ] || mysql_error 'MySQL did not become ready for KFP grants'
fi

if [ -z "$MYSQL_USER" ] || [ -z "$MYSQL_PASSWORD" ]; then
    mysql_error 'KFP database initialization requires MYSQL_USER and MYSQL_PASSWORD'
fi

# The upstream entrypoint grants only MYSQL_DATABASE (metadb) to this user.
docker_process_sql --database=mysql <<-EOSQL
    GRANT ALL PRIVILEGES ON \`mlpipeline\`.* TO '$MYSQL_USER'@'%';
    GRANT ALL PRIVILEGES ON \`cachedb\`.* TO '$MYSQL_USER'@'%';
EOSQL
