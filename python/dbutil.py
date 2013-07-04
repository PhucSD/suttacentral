#!/usr/bin/env python

"""A utility to perform MySQL database functions"""

import colorama, os, sys, plumbum, textwrap
import config

DB_EXPORT_URL = 'http://suttacentral.net/db-exports/sc-latest.sql.gz'
LOCAL_DB_EXPORT_PATH = os.path.join(config.base_dir, 'tmp', 'sc-latest.sql.gz')
NEW_CHANGES_SQL_PATH = os.path.join(config.base_dir, 'db', 'new-python-changes.sql')

def print_notice(str, **kwargs):
    print(colorama.Fore.BLUE, end='')
    print(str, **kwargs)
    print(colorama.Fore.RESET, end='')
    sys.stdout.flush()

def print_error(str, **kwargs):
    print(colorama.Fore.RED, end='')
    print(str, **kwargs)
    print(colorama.Fore.RESET, end='')
    sys.stdout.flush()

def clean(str):
    return textwrap.dedent(str).strip()

def indent(str):
    indent_str = '    '
    return textwrap.fill(str, 80,
        initial_indent=indent_str, subsequent_indent=indent_str)

def fetch_db_cmd():
    return plumbum.local['curl']['-s', '-o', LOCAL_DB_EXPORT_PATH, DB_EXPORT_URL]

def mysql_cmd(root=False, db=False):
    args = [ '-h', config.mysql['host'],
             '-P', str(config.mysql['port']) ]
    if root:
        args += [ '-u', 'root', '-p' ]
    else:
        args += [ '-u', config.mysql['user'],
                 '-p' + config.mysql['password'] ]
    if db:
        args.append(config.mysql['db'])
    return plumbum.local['mysql'][tuple(args)]

def run(cmd, input=None):
    print('Running:')
    print_notice(indent(str(cmd)))
    if input:
        if type(input) is str:
            print('With input:')
            print_notice(indent(input))
            cmd = (cmd << input)
        else: # command
            print('With input command:')
            print_notice(indent(str(input)))
            cmd = (input | cmd)
    returncode, stdout, stderr = cmd.run(retcode=None)
    if returncode != 0:
        print_error('Process exited unexpectedly; returncode %d' % returncode)
    if stderr:
        print('Process stderr:')
        print_error(indent(stderr))
    if stdout:
        print('Process stdout:')
        print_notice(indent(stdout))

def create_db_user():
    print('Creating database user...')
    print_error('   ...when prompted, enter the MySQL root password!')
    sql = clean("""
        CREATE USER %(user)s@%(host)s IDENTIFIED BY '%(password)s';
        FLUSH PRIVILEGES;
    """) % config.mysql
    run(mysql_cmd(root=True), input=sql)

def setup_db_auth():
    print('Setting database authorization...')
    print_error('   ...when prompted, enter the MySQL root password!')
    sql = clean("""
        GRANT ALL PRIVILEGES ON %(db)s.* TO %(user)s@%(host)s;
        FLUSH PRIVILEGES;
    """ % config.mysql)
    run(mysql_cmd(root=True), input=sql)

def fetch_db_export():
    print('Fetching database export...')
    run(fetch_db_cmd())

def create_db():
    print('Creating database...')
    sql = 'CREATE DATABASE %(db)s CHARACTER SET utf8;' % config.mysql
    run(mysql_cmd(), input=sql)

def load_db():
    print('Loading database...')
    input_cmd = plumbum.local['gunzip']['-c', LOCAL_DB_EXPORT_PATH]
    run(mysql_cmd(db=True), input=input_cmd)
    print('Applying changes to work with new Python code...')
    sql = open(NEW_CHANGES_SQL_PATH, 'r').read()
    run(mysql_cmd(db=True), input=sql)

def drop_db():
    print('Dropping database...')
    sql = 'DROP DATABASE IF EXISTS %(db)s;' % config.mysql
    run(mysql_cmd(), input=sql)

def reset_db():
    print('Resetting database...')
    drop_db()
    create_db()
    load_db()

def usage():
    print(clean("""
        Usage: dbutil.py <command>
        Commands:
            create-db-user  - Create the database user
            setup-db-auth   - Set database user authorization
            fetch-db-export - Fetch the latest database export
            create-db       - Create the database
            load-db         - Load the database from the export
            drop-db         - Drop the database
            reset-db        - Drop, create and load the database
    """))

if __name__ == '__main__':

    colorama.init()

    if len(sys.argv) != 2:
        usage()
    elif sys.argv[1] == 'create-db-user':
        create_db_user()
    elif sys.argv[1] == 'setup-db-auth':
        setup_db_auth()
    elif sys.argv[1] == 'fetch-db-export':
        fetch_db_export()
    elif sys.argv[1] == 'create-db':
        create_db()
    elif sys.argv[1] == 'load-db':
        load_db()
    elif sys.argv[1] == 'drop-db':
        drop_db()
    elif sys.argv[1] == 'reset-db':
        reset_db()
    else:
        usage()

    colorama.deinit()
