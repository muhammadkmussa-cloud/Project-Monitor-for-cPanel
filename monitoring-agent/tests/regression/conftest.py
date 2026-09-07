import os
os.environ['RATE_LIMIT_ENABLED']='false'
os.environ['LOCAL_BACKUP_PATH']='/tmp/project-monitor-regression-backups'
os.environ['TELEGRAM_ENABLED']='false'
os.environ['EMAIL_ENABLED']='false'
os.environ['SLACK_ENABLED']='false'

os.environ['JWT_SECRET']='audit-test-secret-with-at-least-32-characters'
os.environ['API_SECRET_KEY']='audit-test-encryption-key'
