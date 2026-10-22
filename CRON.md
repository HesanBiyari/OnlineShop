# Cron: retry digital fulfilment

Replace the paths with the real cPanel values. Full deployment context:
[`docs/DEPLOYMENT_CPANEL.md`](docs/DEPLOYMENT_CPANEL.md).

```cron
*/5 * * * * cd /home/CPANEL_USER/APP_ROOT && /home/CPANEL_USER/virtualenv/APP_NAME/3.11/bin/python manage.py process_orders >> /home/CPANEL_USER/logs/process_orders.log 2>&1
```

The command is idempotent and safe to re-run. It retries paid/processing orders,
assigns digital codes all-or-nothing per line, and marks fully delivered orders
as completed. Check the log after the first runs.
