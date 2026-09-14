"""Private package socket; no request bodies, cookies or query strings in logs."""
bind = "unix:/run/owner-alpha/gunicorn.sock"
pidfile = "/run/owner-alpha/gunicorn.pid"
workers = 2
worker_class = "sync"
timeout = 120
graceful_timeout = 130
umask = 0o077
accesslog = None
errorlog = "/dev/null"
capture_output = False
daemon = True
preload_app = True
limit_request_line = 4094

