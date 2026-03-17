#!/usr/bin/env python3
"""
Cron job setup for sender_tg_app.

Usage:
    python setup_cron.py install
    python setup_cron.py remove
    python setup_cron.py status
"""

import sys
from pathlib import Path
from crontab import CronTab


CRON_SCHEDULE = "*/30 * * * *"
CRON_COMMENT = "tg-memes-sender"


def install_cron_job():
    """Install or update the cron job."""
    project_root = Path(__file__).parent.parent.resolve()
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    cron = CronTab(user=True)
    cron.remove_all(comment=CRON_COMMENT)
    
    # Create command
    python_path = sys.executable
    log_file = logs_dir / "sender_cron.log"
    command = f"cd {project_root} && {python_path} -m sender_tg_app >> {log_file} 2>&1"
    
    # Create job
    job = cron.new(command=command, comment=CRON_COMMENT)
    job.setall(CRON_SCHEDULE)
    
    if not job.is_valid():
        print(f"❌ Invalid cron schedule: '{CRON_SCHEDULE}'")
        return False
    
    cron.write()
    
    print("✅ Cron job installed")
    print(f"   Schedule: {CRON_SCHEDULE}")
    print(f"   Logs: {log_file}")
    print(f"   Next run: {job.schedule().get_next()}")
    return True


def remove_cron_job():
    """Remove the cron job."""
    cron = CronTab(user=True)
    removed = cron.remove_all(comment=CRON_COMMENT)
    cron.write()
    
    if removed > 0:
        print(f"✅ Removed {removed} cron job(s)")
    else:
        print("ℹ️  No cron job found")
    return True


def check_status():
    """Check if the cron job is installed."""
    cron = CronTab(user=True)
    jobs = list(cron.find_comment(CRON_COMMENT))
    
    if jobs:
        print("✅ Cron job installed")
        for job in jobs:
            print(f"   Schedule: {job.slices}")
            print(f"   Enabled: {job.is_enabled()}")
            print(f"   Next run: {job.schedule().get_next()}")
    else:
        print("ℹ️  No cron job installed")
        print(f"   Run: python {Path(__file__).name} install")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_cron.py [install|remove|status]")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "install":
        success = install_cron_job()
    elif command == "remove":
        success = remove_cron_job()
    elif command == "status":
        success = check_status()
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

