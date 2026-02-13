FROM mysql:8.0

# Custom MySQL configuration for Railway
# Prevents crashes due to Railway's volume system and optimizes for cloud environment

RUN echo "[mysqld]" > /etc/mysql/conf.d/railway.cnf && \
    echo "# Disable native AIO (Railway volume compatibility)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "innodb_use_native_aio=0" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Use fsync for disk writes (Railway filesystem compatibility)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "innodb_flush_method=fsync" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Optimize buffer pool for cloud (256MB)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "innodb_buffer_pool_size=268435456" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Optimize log file size (64MB)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "innodb_log_file_size=67108864" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Limit connections for cloud environment" >> /etc/mysql/conf.d/railway.cnf && \
    echo "max_connections=100" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Optimize table cache" >> /etc/mysql/conf.d/railway.cnf && \
    echo "table_open_cache=2000" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Windows compatibility (case-insensitive table names)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "lower_case_table_names=2" >> /etc/mysql/conf.d/railway.cnf

# Use mysql_native_password for Python connector compatibility
CMD ["mysqld", "--default-authentication-plugin=mysql_native_password"]
