# Cron example - replace paths with your cPanel values.
cd /home/CPANEL_USER/ONLINE_SHOP_ROOT && /home/CPANEL_USER/virtualenv/ONLINE_SHOP_ROOT/3.11/bin/python manage.py process_orders >> /home/CPANEL_USER/logs/process_orders.log 2>&1
