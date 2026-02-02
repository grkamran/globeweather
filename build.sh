#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Google credentials (JSON из env → файл)
if [ -n "$GOOGLE_CREDS_JSON" ]; then
  echo "$GOOGLE_CREDS_JSON" > /tmp/gcloud-translate.json
  export GOOGLE_APPLICATION_CREDENTIALS="/tmp/gcloud-translate.json"
fi

python manage.py collectstatic --noinput
python manage.py migrate
