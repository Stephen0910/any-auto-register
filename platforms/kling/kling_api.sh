#!/bin/bash
LOG_DIR=/home/quickStart/logs
PID_FILE=/tmp/kling_api.pid
APP_DIR=/home/openclaw/github/any-auto-register

mkdir -p $LOG_DIR
LOG_FILE=$LOG_DIR/kling_api_$(date +%Y%m%d).log

case "$1" in
  start)
    if [ -f $PID_FILE ] && kill -0 $(cat $PID_FILE) 2>/dev/null; then
      echo "Already running (pid $(cat $PID_FILE))"
      exit 0
    fi
    cd $APP_DIR
    nohup sudo /root/miniforge3/envs/py313/bin/python -m platforms.kling.api_server >> $LOG_FILE 2>&1 &
    echo $! > $PID_FILE
    echo "Started (pid $!), log: $LOG_FILE"
    ;;
  stop)
    [ -f $PID_FILE ] && sudo kill $(cat $PID_FILE) && rm -f $PID_FILE && echo "Stopped" || echo "Not running"
    ;;
  restart)
    $0 stop; sleep 1; $0 start
    ;;
  status)
    [ -f $PID_FILE ] && kill -0 $(cat $PID_FILE) 2>/dev/null && echo "Running (pid $(cat $PID_FILE))" || echo "Not running"
    ;;
  checkin)
    cd $APP_DIR && sudo /root/miniforge3/envs/py313/bin/python -m platforms.kling.import_accounts checkin
    ;;
  stats)
    cd $APP_DIR && sudo /root/miniforge3/envs/py313/bin/python -m platforms.kling.import_accounts stats
    ;;
  add)
    cd $APP_DIR && sudo /root/miniforge3/envs/py313/bin/python -m platforms.kling.import_accounts add --email "$2" --password "$3"
    ;;
  *)
    echo "Usage: $0 start|stop|restart|status|checkin|stats|add <email> <password>"
    ;;
esac
