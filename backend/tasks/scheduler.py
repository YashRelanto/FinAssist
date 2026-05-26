from celery import Celery
from celery.schedules import crontab
from app.utils.scrapers import (
    scheduled_weekly_scrape,
    scheduled_daily_morning_scrape,
    scheduled_daily_evening_scrape,
    scheduled_monthly_scrape
)

# Initialize Celery app
# (You may need to configure your broker, e.g., broker='redis://localhost:6379/0')
celery = Celery('finassist', broker='redis://localhost:6379/0')

@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    
    # BANKING — Every Sunday 2 AM
    sender.add_periodic_task(
        crontab(hour=2, minute=0, day_of_week=0),
        scheduled_weekly_scrape.s(),
        name='Weekly Banking Scrape'
    )
    
    # STOCKS — Mon-Fri 9:15 AM
    sender.add_periodic_task(
        crontab(hour=9, minute=15, day_of_week='1-5'),
        scheduled_daily_morning_scrape.s(),
        name='Daily Morning Stocks Scrape'
    )
    
    # MF + GOLD + TIPS — Daily 6 PM
    sender.add_periodic_task(
        crontab(hour=18, minute=0),
        scheduled_daily_evening_scrape.s(),
        name='Daily Evening MF, Gold & Tips Scrape'
    )
    
    # RETIREMENT — 1st of every month
    sender.add_periodic_task(
        crontab(hour=3, minute=0, day_of_month='1'),
        scheduled_monthly_scrape.s(),
        name='Monthly Retirement Scrape'
    )
